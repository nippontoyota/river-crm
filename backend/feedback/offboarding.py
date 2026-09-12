import hashlib
import json
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User, UserLifecycleEvent
from .models import FeedbackTask
from .services import lock_feedback, reconcile_assignments


def impact(user):
    tasks = FeedbackTask.objects.filter(assigned_to=user, lead__deleted_at__isnull=True)
    payload = [user.pk, user.is_active, str(user.deleted_at), list(tasks.order_by("id").values_list("id", "status", "revision"))]
    return {"version": hashlib.sha256(json.dumps(payload).encode()).hexdigest(), "assignment_role": "FEEDBACK",
        "actionable_count": tasks.filter(status="OPEN").count(), "closed_count": tasks.exclude(status="OPEN").count(),
        "followup_count": 0, "complaint_count": 0, "lead_groups": [], "eligible_users": []}


@transaction.atomic
def offboard(user_id, actor, action, version, reason):
    from accounts.offboarding import OffboardingConflict, _invalidate_user
    lock_feedback()
    user = User.objects.get(pk=user_id)
    if user.deleted_at:
        raise ValidationError("This account no longer exists.")
    if action == "DISABLED" and not user.is_active:
        raise ValidationError("This account is already disabled.")
    reason = reason.strip() if isinstance(reason, str) else ""
    if action == "DELETED" and not reason:
        raise ValidationError({"reason": "A deletion reason is required."})
    if len(reason) > 500:
        raise ValidationError({"reason": "Use 500 characters or fewer."})
    preview = impact(user)
    if preview["version"] != version:
        raise OffboardingConflict("Feedback work changed. Refresh the preview and try again.")
    user.is_active = False
    if action == "DELETED":
        user.email = f"deleted-{user.pk}-{uuid4().hex}@invalid.local"
        user.phone = ""
        user.is_staff = user.is_superuser = False
        user.deleted_at = timezone.now()
        user.set_unusable_password()
        user.groups.clear()
        user.user_permissions.clear()
    user.save()
    _invalidate_user(user)
    reconcile_assignments()
    summary = {"feedback_tasks_redistributed": preview["actionable_count"], "closed_feedback_retained": preview["closed_count"]}
    UserLifecycleEvent.objects.create(user=user, actor=actor, action=action, reason=reason, summary=summary)
    return summary


@transaction.atomic
def enable(user_id, actor):
    lock_feedback()
    user = User.objects.get(pk=user_id)
    if user.deleted_at or user.is_active:
        raise ValidationError("Only disabled, non-deleted accounts can be enabled.")
    user.is_active = True
    user.save(update_fields=["is_active"])
    reconcile_assignments()
    UserLifecycleEvent.objects.create(user=user, actor=actor, action="ENABLED")
    return user
