from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from leads.models import Lead, LeadAudit
from servicing.models import ServiceEvent, ServiceRequest
from .models import FeedbackTask
from .questionnaires import CURRENT_VERSION
from .services import allocate, branch_key, eligible_callers, lock_feedback, morning_after


class HistoricalInput(serializers.Serializer):
    records = serializers.ListField(child=serializers.RegexField(r"^(sale|service):[1-9][0-9]*$"), min_length=1, max_length=200)
    next_call_at = serializers.DateTimeField()

    def validate_next_call_at(self, value):
        if value <= timezone.now():
            raise ValidationError("Choose a future calling date and time.")
        return value


def candidates():
    now = timezone.now()
    since = now - timedelta(days=30)
    rows = []
    audits = LeadAudit.objects.filter(created_at__gte=since, created_at__lte=now,
        event__in=["test_drive_completed", "so_updated", "status_changed"]).select_related("lead").order_by("created_at", "id")
    seen = set()
    for audit in audits:
        kind = None
        occurred = audit.created_at
        if audit.event == "test_drive_completed" and audit.lead.test_drive_completed_at:
            kind, occurred = "TDF", audit.lead.test_drive_completed_at
        elif audit.event in {"so_updated", "status_changed"} and "sales_outcome" in audit.before and audit.before["sales_outcome"] != audit.after.get("sales_outcome"):
            kind = {"BOOKED": "PBF", "RETAILED": "PSF"}.get(audit.after.get("sales_outcome"))
        if not kind or not since <= occurred <= now:
            continue
        existing = FeedbackTask.objects.filter(lead=audit.lead, kind=kind).first()
        reason = "Customer deleted" if audit.lead.deleted_at else "Feedback already exists" if existing else "Earlier qualifying event selected" if (audit.lead_id, kind) in seen else ""
        seen.add((audit.lead_id, kind))
        rows.append({"key": f"sale:{audit.pk}", "kind": kind, "customer": audit.lead.name, "branch": branch_key(audit.lead.branch),
            "occurred_at": occurred, "original_due_at": morning_after(occurred, 3 if kind == "PSF" else 1),
            "exclusion_reason": reason, "existing_task": existing.pk if existing else None, "source": audit})
    events = ServiceEvent.objects.filter(action="resolve", created_at__gte=since, created_at__lte=now).select_related("request").order_by("created_at", "id")
    for event in events:
        if event.before.get("status") not in {"IN_PROGRESS", "WAITING"} or event.after.get("status") != "RESOLVED":
            continue
        existing = FeedbackTask.objects.filter(service_event=event).first()
        reopened = event.request.status != "RESOLVED" or event.request.events.filter(action="reopen", id__gt=event.pk).exists()
        rows.append({"key": f"service:{event.pk}", "kind": "SVC", "customer": event.request.customer_snapshot.get("customer_name", ""),
            "branch": branch_key(event.request.branch), "occurred_at": event.created_at, "original_due_at": morning_after(event.created_at),
            "exclusion_reason": "Feedback already exists" if existing else "Service request reopened after this resolution" if reopened else "",
            "existing_task": existing.pk if existing else None, "source": event})
    return rows


def preview():
    loads = dict(FeedbackTask.objects.filter(status="OPEN", lead__deleted_at__isnull=True).values("assigned_to_id").annotate(n=Count("id")).values_list("assigned_to_id", "n"))
    rows = candidates()
    callers = list(eligible_callers())
    for row in rows:
        row.pop("source")
        caller = min(callers, key=lambda user: (loads.get(user.pk, 0), user.pk)) if callers and not row["exclusion_reason"] else None
        row["proposed_caller"] = {"id": caller.pk, "name": caller.history_display_name} if caller else None
        row["unassigned_reason"] = "No active feedback caller" if not callers else ""
        if caller:
            loads[caller.pk] = loads.get(caller.pk, 0) + 1
    return rows


@transaction.atomic
def import_selected(data, actor):
    keys = set(data["records"])
    # Match normal writers' ordering: source rows, then the shared feedback lock.
    audits = LeadAudit.objects.filter(pk__in=[key.split(":")[1] for key in keys if key.startswith("sale:")])
    list(Lead.objects.select_for_update().filter(pk__in=audits.values("lead_id")).order_by("pk"))
    events = ServiceEvent.objects.filter(pk__in=[key.split(":")[1] for key in keys if key.startswith("service:")])
    list(ServiceRequest.objects.select_for_update().filter(pk__in=events.values("request_id")).order_by("pk"))
    lock_feedback()
    rows = {row["key"]: row for row in candidates()}
    tasks = []
    for key in data["records"]:
        row = rows.get(key)
        if not row:
            raise ValidationError({"records": f"{key} is no longer a verified event in the last 30 days."})
        if row["existing_task"]:
            tasks.append(FeedbackTask.objects.get(pk=row["existing_task"]))
            continue
        if row["exclusion_reason"]:
            raise ValidationError({"records": f"{key}: {row['exclusion_reason']}"})
        source = row["source"]
        task = FeedbackTask.objects.create(kind=row["kind"], branch=row["branch"], occurred_at=row["occurred_at"],
            original_due_at=row["original_due_at"], next_call_at=data["next_call_at"], origin="HISTORICAL", questionnaire_version=CURRENT_VERSION,
            **({"service_event": source} if row["kind"] == "SVC" else {"source_audit": source, "lead": source.lead}))
        allocate(task, "Historical catch-up selected by admin", actor)
        tasks.append(task)
        row["existing_task"] = task.pk
    return tasks
