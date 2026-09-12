from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import FeedbackTask
from .services import lock_feedback, notify, reconcile_assignments


@shared_task
def process_feedback_queue():
    reconcile_assignments()
    with transaction.atomic():
        lock_feedback()
        now = timezone.now()
        for task in FeedbackTask.objects.filter(status="OPEN", assigned_to__isnull=False,
                lead__deleted_at__isnull=True, next_call_at__lte=now).select_related("lead"):
            notify(task, "FEEDBACK_DUE", "Call due")
            if timezone.localdate(task.next_call_at) < timezone.localdate(now):
                notify(task, "FEEDBACK_OVERDUE", "Call overdue")
