from django.db import migrations
from django.db.models import OuterRef, Subquery
from django.utils import timezone


def reclassify_already_booked(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    CallLog = apps.get_model("leads", "CallLog")
    Milestone = apps.get_model("ceo", "Milestone")
    OperationEvent = apps.get_model("ceo", "OperationEvent")
    db = schema_editor.connection.alias

    calls = list(CallLog.objects.using(db).filter(outcome__iexact="Already Booked").order_by("created_at", "pk"))
    if not calls:
        return

    latest_outcome = CallLog.objects.using(db).filter(lead_id=OuterRef("pk")).order_by("-created_at", "-pk").values("outcome")[:1]
    current_ids = list(Lead.objects.using(db).filter(status="LOST", sales_outcome="LOST").annotate(
        latest_outcome=Subquery(latest_outcome),
    ).filter(latest_outcome__iexact="Already Booked").values_list("pk", flat=True))

    CallLog.objects.using(db).filter(pk__in=[call.pk for call in calls], status="LOST").update(status="WALKIN")
    Lead.objects.using(db).filter(pk__in=current_ids).update(status="WALKIN", sales_outcome="BOOKED")

    leads = Lead.objects.using(db).in_bulk({call.lead_id for call in calls})
    for call in calls:
        lead = leads[call.lead_id]
        Milestone.objects.using(db).get_or_create(lead_id=lead.pk, kind="B", defaults={
            "occurred_on": timezone.localdate(call.created_at), "occurred_at": call.created_at,
            "branch": (lead.branch or "").strip().casefold(), "rto": lead.rto, "source": lead.source,
            "campaign": lead.campaign, "activity": lead.activity, "sub_activity": lead.sub_activity,
            "model_interest": lead.model_interest, "cre_id": lead.assigned_so_id, "so_id": lead.assigned_ps_id,
            "actor_id": call.so_id, "provenance": "corrected",
        })
        event = OperationEvent.objects.using(db).filter(source_key=f"call:{call.pk}").first()
        if event:
            event.after = {**event.after, "status": "WALKIN"}
            event.snapshot = {**event.snapshot, "status": "WALKIN"}
            event.save(update_fields=["after", "snapshot"])


class Migration(migrations.Migration):
    dependencies = [("ceo", "0002_backfill_verified_history"), ("leads", "0021_inbound_call_center")]
    operations = [migrations.RunPython(reclassify_already_booked, migrations.RunPython.noop)]
