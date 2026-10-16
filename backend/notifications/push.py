import json
import logging

from django.conf import settings
from django.db import transaction

from accounts.models import User
from .models import Notification, PushSubscription

logger = logging.getLogger(__name__)


def push_is_configured():
    return bool(
        settings.WEB_PUSH_VAPID_PUBLIC_KEY
        and settings.WEB_PUSH_VAPID_PRIVATE_KEY
        and settings.WEB_PUSH_VAPID_SUBJECT
    )


def schedule_assignment_pushes(notifications):
    if not push_is_configured():
        return
    notification_ids = [item.pk for item in notifications if item.pk and item.kind == Notification.Kind.ASSIGNMENT]
    if not notification_ids:
        return

    def enqueue():
        from .tasks import deliver_assignment_pushes
        deliver_assignment_pushes.delay(notification_ids)

    transaction.on_commit(enqueue)


def deliver_assignment_push(notification_id):
    if not push_is_configured():
        return 0
    notification = Notification.objects.select_related("user", "lead").filter(
        pk=notification_id,
        kind=Notification.Kind.ASSIGNMENT,
        user__role=User.Role.SALES_OFFICER,
        user__is_active=True,
        user__deleted_at__isnull=True,
    ).first()
    if not notification:
        return 0

    from pywebpush import WebPushException, webpush

    url = f"/my-leads?lead={notification.lead_id}" if notification.lead_id else "/my-leads"
    payload = json.dumps({
        "title": "New lead assigned",
        "body": notification.message,
        "url": url,
        "tag": f"lead-assignment-{notification.pk}",
    })
    delivered = 0
    for subscription in list(PushSubscription.objects.filter(user=notification.user)):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.WEB_PUSH_VAPID_SUBJECT},
                ttl=86_400,
            )
            delivered += 1
        except WebPushException as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code in {404, 410}:
                subscription.delete()
            else:
                logger.warning("Web Push delivery failed for subscription %s: %s", subscription.pk, error)
    return delivered
