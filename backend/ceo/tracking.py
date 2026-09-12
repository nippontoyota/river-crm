from django.utils import timezone

from .models import Milestone, OperationEvent


def branch_key(value):
    return (value or "").strip().casefold()


def lead_snapshot(lead):
    return {"branch": branch_key(lead.branch), "rto": lead.rto, "source": lead.source, "campaign": lead.campaign,
            "activity": lead.activity, "sub_activity": lead.sub_activity, "model_interest": lead.model_interest,
            "cre_id": lead.assigned_so_id, "so_id": lead.assigned_ps_id, "status": lead.status, "category": lead.category}


def milestone(lead, kind, actor=None, occurred_at=None):
    moment = occurred_at or timezone.now()
    snapshot = lead_snapshot(lead)
    snapshot.pop("status")
    snapshot.pop("category")
    occurred_on = lead.enquiry_date if kind == "E" else timezone.localdate(moment)
    return Milestone.objects.get_or_create(lead=lead, kind=kind, defaults={**snapshot, "actor": actor,
        "occurred_on": occurred_on, "occurred_at": None if kind == "E" else moment})[0]


def record_audit(audit):
    from feedback.services import record_audit as record_feedback_audit
    record_feedback_audit(audit)
    lead = audit.lead
    snapshot = lead_snapshot(lead)
    OperationEvent.objects.get_or_create(source_key=f"audit:{audit.pk}", defaults={
        "lead": lead, "actor": audit.actor, "kind": audit.event, "occurred_at": audit.created_at,
        "branch": snapshot["branch"], "snapshot": snapshot, "before": audit.before, "after": audit.after})
    if audit.event in {"created", "imported"}:
        milestone(lead, "E", audit.actor)
    if audit.event == "test_drive_completed" and lead.test_drive_completed_at:
        milestone(lead, "T", audit.actor, lead.test_drive_completed_at)
    before, after = audit.before, audit.after
    if "enquiry_date" in after and before.get("enquiry_date") != after["enquiry_date"]:
        Milestone.objects.filter(lead=lead, kind="E").update(occurred_on=lead.enquiry_date)

    if audit.event in {"so_updated", "status_changed"}:
        if (after.get("sales_outcome") == "BOOKED" and before.get("sales_outcome") != "BOOKED") or (after.get("status") == "WALKIN" and before.get("status") != "WALKIN"):
            milestone(lead, "B", audit.actor, audit.created_at)
        if (after.get("sales_outcome") == "RETAILED" and before.get("sales_outcome") != "RETAILED") or (after.get("status") == "WON" and before.get("status") != "WON"):
            milestone(lead, "R", audit.actor, audit.created_at)
        if before.get("sales_outcome") == "BOOKED" and after.get("sales_outcome") == "LOST":
            OperationEvent.objects.get_or_create(source_key=f"cancel:{audit.pk}", defaults={"lead": lead,
                "actor": audit.actor, "kind": "booking_cancelled", "occurred_at": audit.created_at,
                "branch": snapshot["branch"], "snapshot": snapshot, "before": before, "after": after})


def complaint_event(complaint, actor, kind, before=None):
    OperationEvent.objects.create(complaint=complaint, lead=complaint.related_lead, actor=actor, kind=kind,
        occurred_at=timezone.now(), source_key=f"complaint:{complaint.pk}:{timezone.now().isoformat()}",
        branch=branch_key(complaint.branch), before=before or {}, after={"status": complaint.status,
        "priority": complaint.priority, "assigned_to_id": complaint.assigned_to_id})
