from django.db.models.signals import post_save
from django.dispatch import receiver

from leads.models import LeadAudit
from .whatsapp import record_lead_audit


@receiver(post_save, sender=LeadAudit)
def whatsapp_audit_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record_lead_audit(instance)
