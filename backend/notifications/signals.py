from django.db.models.signals import post_save
from django.dispatch import receiver

from leads.models import LeadAudit
from .models import Notification
from .push import schedule_assignment_pushes
from .whatsapp import record_lead_audit


@receiver(post_save, sender=LeadAudit)
def whatsapp_audit_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record_lead_audit(instance)


@receiver(post_save, sender=Notification)
def assignment_notification_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        schedule_assignment_pushes([instance])
