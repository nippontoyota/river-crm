from celery import shared_task
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from leads.models import FollowUp
from .models import Notification


@shared_task
def create_due_follow_up_notifications():
    due_ids = FollowUp.objects.filter(
        resolved_at__isnull=True,
        notified_at__isnull=True,
        reminder_held=False,
        scheduled_for__lte=timezone.now(),
        lead__deleted_at__isnull=True,
        so__is_active=True,
        so__deleted_at__isnull=True,
    ).values_list("id", "so_id")
    for follow_up_id, owner_id in due_ids:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=owner_id)
            follow_up = FollowUp.objects.select_for_update().select_related("lead", "so").filter(
                pk=follow_up_id,
                so_id=owner_id,
                resolved_at__isnull=True,
                notified_at__isnull=True,
                reminder_held=False,
                scheduled_for__lte=timezone.now(),
                lead__deleted_at__isnull=True,
                so__is_active=True,
                so__deleted_at__isnull=True,
            ).first()
            if not follow_up:
                continue
            kind = Notification.Kind.OVERDUE if follow_up.scheduled_for < timezone.now() else Notification.Kind.FOLLOW_UP
            Notification.objects.create(user=follow_up.so, lead=follow_up.lead, kind=kind, message=f"Follow up with {follow_up.lead.name}.")
            follow_up.notified_at = timezone.now()
            follow_up.save(update_fields=["notified_at"])
