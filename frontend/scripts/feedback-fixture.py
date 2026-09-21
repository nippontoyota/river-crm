"""Create isolated browser data. Never reads production environment files."""
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.environ["DATABASE_URL"] = "sqlite:////tmp/crm-feedback-browser.sqlite3"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_SECRET_KEY"] = "feedback-browser-local-secret-with-at-least-32-characters"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1:3039,http://127.0.0.1:3038"
os.environ["CSRF_TRUSTED_ORIGINS"] = "http://127.0.0.1:3039,http://127.0.0.1:3038"
os.environ["DJANGO_ALLOWED_HOSTS"] = "127.0.0.1,localhost"
import django
django.setup()
from django.core.management import call_command
from django.utils import timezone
from accounts.models import User
from leads.models import Lead, LeadAudit, SystemConfig
from feedback.models import FeedbackState, FeedbackRequest
from feedback.services import record_service_event
from feedback.tasks import process_feedback_queue
from servicing.models import ServiceEvent, ServiceRequest, Vehicle

if len(sys.argv) > 1 and sys.argv[1] == "serve":
    sys.stdout = open("/tmp/crm-feedback-api-server.log", "a", buffering=1)
    sys.stderr = sys.stdout
    call_command("runserver", "127.0.0.1:8039", use_reloader=False)
else:
    call_command("migrate", verbosity=0)
    if User.objects.filter(email="caller@feedback-browser.test").exists():
        raise SystemExit("Fixture already exists. Use a fresh /tmp/crm-feedback-browser.sqlite3.")
    now = timezone.now()
    FeedbackState.objects.filter(pk=1).update(activated_at=now - timedelta(days=3))
    SystemConfig.objects.create(lists={"branches": ["Kochi", "Thrissur"], "models": ["Indie"]})
    users = {}
    for name, role, branch in [("caller", "FEEDBACK", "Kochi"), ("ceo", "CEO", ""), ("admin", "ADMIN", ""), ("manager", "SALES_MANAGER", "Kochi"), ("so", "SO", "Kochi"), ("service", "SERVICE", "Kochi")]:
        users[name] = User.objects.create_user(f"{name}@feedback-browser.test", "FeedbackBrowser123!", first_name="Asha" if name == "caller" else name.title(), role=role, location=branch)
    with patch("django.utils.timezone.now", return_value=now - timedelta(days=2)):
        lead = Lead.objects.create(name="Anjali Menon", phone="9876500000", branch="Kochi", assigned_ps=users["so"], test_drive_completed_at=now - timedelta(days=2))
        LeadAudit.objects.create(lead=lead, actor=users["so"], event="test_drive_completed", before={"test_drive_completed_at": None}, after={"test_drive_completed_at": lead.test_drive_completed_at.isoformat()})
        vehicle = Vehicle.objects.create(chassis_number="FEEDBACKBROWSER01", model="Indie", customer_name="Service Customer", customer_phone="9876500001", created_by=users["service"])
        request = ServiceRequest.objects.create(vehicle=vehicle, branch="Kochi", status="RESOLVED", issue="Brake noise", resolution_notes="Brake adjusted", resolved_at=timezone.now(), customer_snapshot=vehicle.customer(), vehicle_snapshot={"model": "Indie", "chassis_number": vehicle.chassis_number}, created_by=users["service"])
        event = ServiceEvent.objects.create(request=request, actor=users["service"], action="resolve", before={"status": "IN_PROGRESS"}, after={"status": "RESOLVED"}, note="Brake adjusted")
        record_service_event(event)
    FeedbackRequest.objects.create(lead=lead, requested_by=users["so"], reason="Check delivery concern", preferred_at=now + timedelta(days=1))
    with patch("django.utils.timezone.now", return_value=now - timedelta(days=7)):
        historical = Lead.objects.create(name="Historical Customer", phone="9876500002", branch="Kochi", assigned_ps=users["so"])
        LeadAudit.objects.create(lead=historical, event="so_updated", before={"sales_outcome": "PENDING"}, after={"sales_outcome": "BOOKED"})
    process_feedback_queue()
    print("PASS: isolated feedback fixture created")
