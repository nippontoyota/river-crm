import hashlib
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User, UserLifecycleEvent


def impact(user):
    version = hashlib.sha256(f"{user.pk}:{user.is_active}:{user.deleted_at}:{user.location}".encode()).hexdigest()
    return {"version": version, "assignment_role": "SERVICE", "actionable_count": 0, "closed_count": 0,
        "followup_count": 0, "complaint_count": 0, "lead_groups": [], "eligible_users": []}


@transaction.atomic
def offboard(user_id, actor, action, version, reason):
    from accounts.offboarding import OffboardingConflict, _invalidate_user
    user = User.objects.select_for_update().get(pk=user_id)
    if user.deleted_at or (action == "DISABLED" and not user.is_active):
        raise ValidationError("This account is already disabled or deleted.")
    if impact(user)["version"] != version:
        raise OffboardingConflict("The account changed. Refresh the preview.")
    reason = reason.strip() if isinstance(reason, str) else ""
    if (action == "DELETED" and not reason) or len(reason) > 500:
        raise ValidationError({"reason": "Provide a deletion reason of up to 500 characters."})
    user.is_active = False
    if action == "DELETED":
        user.deleted_at = timezone.now()
        user.email = f"deleted-{user.pk}-{uuid4().hex}@invalid.local"
        user.phone = ""
        user.is_staff = user.is_superuser = False
        user.set_unusable_password()
        user.groups.clear()
        user.user_permissions.clear()
    user.save()
    _invalidate_user(user)
    summary = {"branch_queue_retained": user.location}
    UserLifecycleEvent.objects.create(user=user, actor=actor, action=action, reason=reason, summary=summary)
    return summary


@transaction.atomic
def enable(user_id, actor):
    user = User.objects.select_for_update().get(pk=user_id)
    if user.deleted_at or user.is_active:
        raise ValidationError("Only disabled accounts can be enabled.")
    user.is_active = True
    user.save(update_fields=["is_active"])
    UserLifecycleEvent.objects.create(user=user, actor=actor, action="ENABLED")
    return user
