from django.db.models.signals import post_save
from django.dispatch import receiver

from leads.models import CallLog, FollowUp, LeadAudit
from .models import OperationEvent
from .tracking import lead_snapshot, record_audit


@receiver(post_save, sender=LeadAudit)
def audit_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record_audit(instance)


@receiver(post_save, sender=CallLog)
def call_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        snapshot = lead_snapshot(instance.lead)
        OperationEvent.objects.create(lead=instance.lead, actor=instance.so, kind="call", occurred_at=instance.created_at,
            source_key=f"call:{instance.pk}", branch=snapshot["branch"], snapshot=snapshot,
            after={"call_status": instance.call_status, "outcome": instance.outcome, "status": instance.status, "remarks": instance.remarks})


@receiver(post_save, sender=FollowUp)
def followup_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        snapshot = lead_snapshot(instance.lead)
        OperationEvent.objects.create(lead=instance.lead, actor=instance.so, kind="followup_scheduled", occurred_at=instance.created_at,
            source_key=f"followup:{instance.pk}", branch=snapshot["branch"], snapshot=snapshot,
            after={"scheduled_for": str(instance.scheduled_for), "followup_id": instance.pk})


from complaints.models import ComplaintNote
from .models import FinancialEntry
from .tracking import branch_key


@receiver(post_save, sender=ComplaintNote)
def complaint_note_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        complaint = instance.complaint
        OperationEvent.objects.create(complaint=complaint, lead=complaint.related_lead, actor=instance.author,
            kind="complaint_note", occurred_at=instance.created_at, source_key=f"complaint-note:{instance.pk}",
            branch=branch_key(complaint.branch), after={"content": instance.content})


@receiver(post_save, sender=FinancialEntry)
def financial_entry_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        OperationEvent.objects.create(lead=instance.account.lead, actor=instance.actor, kind="finance_" + instance.kind.lower(),
            occurred_at=instance.created_at, source_key=f"finance:{instance.pk}", branch=instance.branch,
            before=instance.before, after={**{key: value for key, value in instance.after.items() if key != "request"},
            "amount": str(instance.amount), "occurred_on": str(instance.occurred_on), "notes": instance.notes,
            "method": instance.method, "reference": instance.reference, "reverses": instance.reverses_id})
