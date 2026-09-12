from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    Audit = apps.get_model("leads", "LeadAudit")
    Call = apps.get_model("leads", "CallLog")
    FollowUp = apps.get_model("leads", "FollowUp")
    Complaint = apps.get_model("complaints", "Complaint")
    Note = apps.get_model("complaints", "ComplaintNote")
    Milestone = apps.get_model("ceo", "Milestone")
    Event = apps.get_model("ceo", "OperationEvent")
    db = schema_editor.connection.alias
    # A current branch/owner is not evidence of historical attribution.
    # Preserve unknown snapshots instead of attributing past work to today's team.
    for lead in Lead.objects.using(db).iterator(chunk_size=500):
        Milestone.objects.using(db).get_or_create(lead_id=lead.pk, kind="E", defaults={"occurred_on": lead.enquiry_date, "provenance": "legacy"})
        if lead.test_drive_completed_at:
            Milestone.objects.using(db).get_or_create(lead_id=lead.pk, kind="T", defaults={"occurred_on": timezone.localdate(lead.test_drive_completed_at), "occurred_at": lead.test_drive_completed_at, "provenance": "legacy"})
    for audit in Audit.objects.using(db).order_by("created_at", "id").iterator(chunk_size=500):
        Event.objects.using(db).get_or_create(source_key=f"audit:{audit.pk}", defaults={"lead_id": audit.lead_id, "actor_id": audit.actor_id,
            "kind": audit.event, "occurred_at": audit.created_at, "before": audit.before, "after": audit.after, "provenance": "legacy"})
        if audit.event in {"created", "imported"}:
            Milestone.objects.using(db).filter(lead_id=audit.lead_id, kind="E", actor_id__isnull=True).update(actor_id=audit.actor_id)
        if audit.event not in {"so_updated", "status_changed"}:
            continue
        for kind, status, outcome in [("B", "WALKIN", "BOOKED"), ("R", "WON", "RETAILED")]:
            changed = ("status" in audit.before and audit.before["status"] != status and audit.after.get("status") == status) or ("sales_outcome" in audit.before and audit.before["sales_outcome"] != outcome and audit.after.get("sales_outcome") == outcome)
            if changed:
                Milestone.objects.using(db).get_or_create(lead_id=audit.lead_id, kind=kind, defaults={"occurred_at": audit.created_at,
                    "occurred_on": timezone.localdate(audit.created_at), "actor_id": audit.actor_id, "provenance": "legacy"})
        if audit.before.get("sales_outcome") == "BOOKED" and audit.after.get("sales_outcome") == "LOST":
            Event.objects.using(db).get_or_create(source_key=f"cancel:{audit.pk}", defaults={"lead_id": audit.lead_id, "actor_id": audit.actor_id,
                "kind": "booking_cancelled", "occurred_at": audit.created_at, "before": audit.before, "after": audit.after, "provenance": "legacy"})
    for call in Call.objects.using(db).iterator(chunk_size=500):
        Event.objects.using(db).get_or_create(source_key=f"call:{call.pk}", defaults={"lead_id": call.lead_id, "actor_id": call.so_id,
            "kind": "call", "occurred_at": call.created_at, "provenance": "legacy",
            "after": {"call_status": call.call_status, "outcome": call.outcome, "status": call.status, "remarks": call.remarks}})
    for item in FollowUp.objects.using(db).iterator(chunk_size=500):
        Event.objects.using(db).get_or_create(source_key=f"followup:{item.pk}", defaults={"lead_id": item.lead_id,
            "kind": "followup_scheduled", "occurred_at": item.created_at, "provenance": "legacy",
            "after": {"scheduled_for": item.scheduled_for.isoformat(), "followup_id": item.pk, "owner_id": item.so_id}})
        if item.resolved_at:
            Event.objects.using(db).get_or_create(source_key=f"followup-resolved:{item.pk}", defaults={"lead_id": item.lead_id,
                "kind": "followup_resolved", "occurred_at": item.resolved_at, "provenance": "legacy",
                "after": {"scheduled_for": item.scheduled_for.isoformat(), "followup_id": item.pk, "owner_id": item.so_id}})
    for item in Complaint.objects.using(db).iterator(chunk_size=500):
        Event.objects.using(db).get_or_create(source_key=f"complaint-created:{item.pk}", defaults={"complaint_id": item.pk, "lead_id": item.related_lead_id,
            "kind": "complaint_created", "actor_id": item.logged_by_id, "occurred_at": item.created_at, "provenance": "legacy", "after": {"subject": item.subject}})
        if item.resolved_at:
            Event.objects.using(db).get_or_create(source_key=f"complaint-resolved:{item.pk}", defaults={"complaint_id": item.pk, "lead_id": item.related_lead_id,
                "kind": "complaint_resolved", "occurred_at": item.resolved_at, "provenance": "legacy"})
    for note in Note.objects.using(db).select_related("complaint").iterator(chunk_size=500):
        Event.objects.using(db).get_or_create(source_key=f"complaint-note:{note.pk}", defaults={"complaint_id": note.complaint_id,
            "lead_id": note.complaint.related_lead_id, "kind": "complaint_note", "actor_id": note.author_id,
            "occurred_at": note.created_at, "provenance": "legacy", "after": {"content": note.content}})


class Migration(migrations.Migration):
    dependencies = [("ceo", "0001_initial")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
