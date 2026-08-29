from celery import shared_task
from django.utils import timezone

from leads.models import FollowUp
from .models import Notification


@shared_task
def create_due_follow_up_notifications():
    due = FollowUp.objects.filter(resolved_at__isnull=True, notified_at__isnull=True, scheduled_for__lte=timezone.now()).select_related("lead", "so")
    for follow_up in due:
        kind = Notification.Kind.OVERDUE if follow_up.scheduled_for < timezone.now() else Notification.Kind.FOLLOW_UP
        Notification.objects.create(user=follow_up.so, lead=follow_up.lead, kind=kind, message=f"Follow up with {follow_up.lead.name}.")
        follow_up.notified_at = timezone.now()
        follow_up.save(update_fields=["notified_at"])
