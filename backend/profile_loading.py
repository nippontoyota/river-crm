"""Synthetic all-role API benchmark; always uses a disposable in-memory database.

Run: backend/.venv/bin/python backend/profile_loading.py --output /tmp/loading.json
This measures Django/serialization, not production network or browser rendering.
"""
import argparse
import json
import os
import statistics
import subprocess
import types
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

# Never inherit database, queue, storage or cache connections from a deployment.
os.environ.update(DATABASE_URL="sqlite:///:memory:", DJANGO_SETTINGS_MODULE="config.settings",
                  CACHE_URL="", CACHE_TTL_SECONDS="0", DJANGO_DEBUG="false",
                  DJANGO_ALLOWED_HOSTS="testserver", DJANGO_SECURE_SSL_REDIRECT="false",
                  INTAKE_ENABLED="false", WHATSAPP_MODE="disabled")

import django
django.setup()

from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from complaints.models import Complaint
from feedback.models import FeedbackState, FeedbackTask
from leads.models import CallLog, FollowUp, Lead, LeadAudit, SystemConfig
from servicing.models import ServiceEvent, ServiceRequest, Vehicle
from uploads.models import UploadBatch, UploadRow


def seed():
    call_command("migrate", verbosity=0, interactive=False)
    now = timezone.now()
    users = {role: User.objects.create_user(f"{role.lower()}@benchmark.invalid", role=role,
             first_name=label, location="Kochi") for role, label in User.Role.choices}
    SystemConfig.objects.update_or_create(pk=1, defaults={"lists": {
        "branches": ["Kochi"], "sources": ["WALKIN", "WEBSITE"], "models": ["Indie"]}})
    FeedbackState.objects.update_or_create(pk=1, defaults={"activated_at": now - timedelta(days=30)})
    leads = Lead.objects.bulk_create([Lead(name=f"Benchmark {i}", phone=f"9{i:09d}",
        branch="Kochi", source="WALKIN" if i % 2 else "WEBSITE", model_interest="Indie",
        enquiry_date=timezone.localdate(now), assigned_so=users["CRE"], assigned_ps=users["SO"],
        generated_by=users["RECEPTIONIST"] if i % 2 else None,
        status="PENDING" if i % 2 else "QUALIFIED") for i in range(200)])
    CallLog.objects.bulk_create([CallLog(lead=lead, so=users[role], status="PENDING",
        outcome="Call Me Back") for lead in leads for role in ["CRE", "SO"] for _ in range(5)])
    FollowUp.objects.bulk_create([FollowUp(lead=lead, so=users[role], scheduled_for=now - timedelta(hours=i))
        for lead in leads for role in ["CRE", "SO"] for i in range(2)])
    for i, lead in enumerate(leads[:20]):
        Complaint.objects.create(ticket_number=f"CMP-BENCH-{i}", customer_name=lead.name,
            customer_phone=lead.phone, category="OTHER", subject="Benchmark", description="Synthetic",
            branch="Kochi", logged_by=users["CRE"] if i % 2 else users["RECEPTIONIST"],
            assigned_to=users["COMPLAINTS"], related_lead=lead)
        vehicle = Vehicle.objects.create(chassis_number=f"BENCH-{i}", model="Indie",
            related_lead=lead, customer_name=lead.name, customer_phone=lead.phone, created_by=users["CRE"])
        request = ServiceRequest.objects.create(vehicle=vehicle, branch="Kochi", issue="Synthetic",
            status="FORWARDED", created_by=users["CRE"], customer_snapshot={"customer_name": lead.name,
            "customer_phone": lead.phone}, vehicle_snapshot={"model": "Indie"})
        ServiceEvent.objects.bulk_create([ServiceEvent(request=request, actor=users["SERVICE"],
            action="note", note="Synthetic history") for _ in range(5)])
    audits = LeadAudit.objects.bulk_create([LeadAudit(lead=lead, actor=users["SO"], event="benchmark") for lead in leads[:40]])
    FeedbackTask.objects.bulk_create([FeedbackTask(lead=audit.lead, source_audit=audit, kind="TDF",
        branch="Kochi", assigned_to=users["FEEDBACK"], occurred_at=now - timedelta(days=1),
        original_due_at=now - timedelta(hours=1), next_call_at=now - timedelta(hours=1)) for audit in audits])
    for i in range(5):
        batch = UploadBatch.objects.create(filename=f"synthetic-{i}.csv", storage_path="",
            uploaded_by=users["META_UPLOADER"], status="COMMITTED", total_rows=10, parsed_ok=10, committed_at=now)
        UploadRow.objects.bulk_create([UploadRow(batch=batch, row_number=j + 1, resolution="IMPORT") for j in range(10)])
    return users


def paths(role):
    result = ["/api/auth/me/"]
    if role not in {"META_UPLOADER", "FEEDBACK"}:
        result += ["/api/system-config/"]
    if role == "ADMIN":
        result += ["/api/leads/?unassigned=true", "/api/leads/", "/api/leads/?q=Benchmark",
            "/api/leads/1/", "/api/leads/unassigned-ce-count/", "/api/analytics/admin/",
            "/api/auth/cre-users/", "/api/auth/sales-officers/", "/api/auth/users/",
            "/api/intake/connections/", "/api/intake/forms/", "/api/intake/submissions/",
            "/api/call-center/summary/", "/api/call-center/leads/1/"]
    if role in {"CRE", "SO"}:
        result += ["/api/leads/my-dashboard/?section=fresh", "/api/leads/my-dashboard/?section=all",
            "/api/leads/my-dashboard/?section=followups", "/api/leads/my-dashboard/?section=all&q=Benchmark",
            "/api/leads/1/", "/api/analytics/me/"]
    if role == "CRE":
        result += ["/api/call-center/leads/1/", "/api/call-center/leads/1/tickets/"]
    if role == "SALES_MANAGER":
        result += ["/api/analytics/sales-manager/?include=filters,ps,source,lost",
            "/api/analytics/sales-manager/ps-followups/", "/api/leads/manager-leads/",
            "/api/leads/manager-leads/?q=Benchmark", "/api/leads/1/"]
    if role == "CEO":
        result += [f"/api/ceo/{section}/" for section in ["options", "overview", "branches", "people", "leads", "segments", "complaints", "ce-performance"]]
        result += ["/api/ceo/leads/1/", "/api/ceo/leads/1/history/"]
    if role == "RECEPTIONIST":
        result += ["/api/analytics/receptionist/", "/api/auth/sales-officers/?location=Kochi"]
    if role in {"ADMIN", "CRE", "RECEPTIONIST", "COMPLAINTS"}:
        result += ["/api/complaints/", "/api/complaints/?q=Benchmark",
                   f"/api/complaints/{2 if role == 'CRE' else 1}/"]
    if role in {"ADMIN", "COMPLAINTS"}:
        result += ["/api/complaints/analytics/"]
    if role in {"ADMIN", "CEO", "SALES_MANAGER", "FEEDBACK"}:
        result += ["/api/feedback/", "/api/feedback/options/", "/api/feedback/summary/",
            "/api/feedback/1/"]
    if role in {"ADMIN", "CEO", "SALES_MANAGER"}:
        result += ["/api/feedback-requests/"]
    if role in {"ADMIN", "CEO", "CRE", "SERVICE"}:
        result += ["/api/service-requests/", "/api/service-requests/?q=Benchmark",
            "/api/service-requests/1/", "/api/vehicles/?chassis=BENCH-0", "/api/vehicles/1/?chassis=BENCH-0"]
    if role in {"ADMIN", "META_UPLOADER"}:
        result += ["/api/uploads/summary/", "/api/uploads/1/", "/api/uploads/1/rows/?filter=duplicates"]
    return result


def baseline_queries(ref):
    """Load only the three previous query implementations for a paired comparison."""
    modules = {}
    for package in ("leads", "analytics", "servicing"):
        source = subprocess.check_output(["git", "show", f"{ref}:backend/{package}/views.py"],
            cwd=Path(__file__).resolve().parent.parent, text=True)
        module = types.ModuleType(f"{package}._loading_baseline")
        module.__package__ = package
        exec(compile(source, f"{ref}:backend/{package}/views.py", "exec"), module.__dict__)
        modules[package] = module
    return [
        ("leads.views.LeadViewSet.get_queryset", modules["leads"].LeadViewSet.get_queryset),
        ("analytics.views.team_metrics", modules["analytics"].team_metrics),
        ("servicing.views.ServiceRequestViewSet.get_queryset", modules["servicing"].ServiceRequestViewSet.get_queryset),
    ]


def stable_payload(value):
    if isinstance(value, dict):
        return {key: stable_payload(item) for key, item in value.items() if key != "generated_at"}
    if isinstance(value, list):
        return [stable_payload(item) for item in value]
    return value


def measure(client, path):
    count = 0
    def count_query(execute, sql, params, many, context):
        nonlocal count
        count += 1
        return execute(sql, params, many, context)
    started = perf_counter()
    with connection.execute_wrapper(count_query):
        response = client.get(path)
        body = b"".join(response.streaming_content) if response.streaming else response.content
    elapsed = round((perf_counter() - started) * 1000, 3)
    return elapsed, count, response.status_code, len(body), stable_payload(json.loads(body))


def summarize(role, path, samples):
    times, queries, statuses, sizes, _ = zip(*samples)
    return dict(role=role, path=path, median_ms=statistics.median(times), min_ms=min(times),
        max_ms=max(times), samples_ms=times, queries=queries, statuses=statuses, bytes=sizes)


def run(repeats, baseline_ref=None):
    users = seed()
    baseline = baseline_queries(baseline_ref) if baseline_ref else []
    rows, before_rows, comparisons = [], [], []
    for role, user in users.items():
        client = APIClient()
        client.force_authenticate(user)
        for path in paths(role):
            samples, before = [], []
            for _ in range(repeats):
                if baseline:
                    with ExitStack() as stack:
                        for target, implementation in baseline:
                            stack.enter_context(patch(target, implementation))
                        before.append(measure(client, path))
                samples.append(measure(client, path))
            rows.append(summarize(role, path, samples))
            if baseline:
                before_rows.append(summarize(role, path, before))
                comparisons.append(dict(role=role, path=path,
                    payload_equal=all(old[4] == new[4] for old, new in zip(before, samples))))
    return {"environment": "isolated in-memory SQLite; synthetic data; cache bypass; forced authentication",
        "limitations": ["Not live role timings", "Excludes network, login and browser rendering",
                        "SQLite query plans differ from production PostgreSQL", "No production data or external services used"],
        "fixture": {"roles": 10, "leads": 200, "calls": 2000, "followups": 800,
                    "complaints": 20, "service_requests": 20, "service_events": 100, "feedback_tasks": 40, "uploads": 5},
        "repetitions": repeats, "results": rows, "baseline_ref": baseline_ref,
        "comparison_method": "alternating previous/current query implementations against identical fixtures; only generated_at excluded from payload equality",
        "baseline_results": before_rows, "comparisons": comparisons}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--baseline-ref", help="Git ref containing the previous query implementations, e.g. HEAD")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    with override_settings(REST_FRAMEWORK={**django.conf.settings.REST_FRAMEWORK,
                                          "DEFAULT_THROTTLE_CLASSES": []}):
        report = run(args.repeats, args.baseline_ref)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    errors = [row for row in report["results"] + report["baseline_results"] if set(row["statuses"]) != {200}]
    print(f"Measured {len(report['results'])} role/endpoint combinations; {len(errors)} non-200 results. Report: {args.output}")
    for row in errors:
        print(row["role"], row["path"], row["statuses"])
    differences = []
    if args.baseline_ref:
        differences = [row for row in report["comparisons"] if not row["payload_equal"]]
        print(f"Payload differences excluding generated_at: {len(differences)}")
        for row in differences:
            print(row["role"], row["path"])
    raise SystemExit(bool(errors or differences))
