from django.db.models import F, Q
from django.db.models.functions import Lower, Trim
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import FeedbackTask
from .services import branch_key


class FeedbackPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or user.deleted_at:
            return False
        if user.role == "CEO":
            return request.method in SAFE_METHODS
        if user.role not in {"ADMIN", "SALES_MANAGER", "FEEDBACK"}:
            return False
        if view.action == "attempt":
            return user.role == "FEEDBACK"
        if view.action == "reassign":
            return user.role in {"ADMIN", "SALES_MANAGER"}
        return request.method in SAFE_METHODS


def visible_tasks(user):
    tasks = FeedbackTask.objects.filter(lead__deleted_at__isnull=True).annotate(
        live_branch=Lower(Trim("lead__branch")))
    if user.role in {"ADMIN", "CEO"}:
        return tasks
    branch = branch_key(user.location)
    if not branch:
        return tasks.none()
    if user.role == "SALES_MANAGER":
        return tasks.filter(Q(status="OPEN", live_branch=branch) | (~Q(status="OPEN") & Q(branch=branch)))
    if user.role == "FEEDBACK":
        return tasks.filter(assigned_to=user, branch=branch, live_branch=F("branch"))
    return tasks.none()
