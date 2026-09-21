from django.db.models import Case, CharField, F, Q, When
from django.db.models.functions import Lower, Trim
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import FeedbackTask
from .services import branch_key


class FeedbackPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or user.deleted_at:
            return False
        if view.action in {"historical_preview", "historical_import"}:
            return user.role == "ADMIN"
        if user.role == "CEO":
            return request.method in SAFE_METHODS
        if user.role not in {"ADMIN", "SALES_MANAGER", "FEEDBACK"}:
            return False
        if view.action == "attempt":
            return user.role == "FEEDBACK"
        if view.action == "complaint":
            return user.role == "FEEDBACK"
        if view.action in {"reassign", "issue"}:
            return user.role in {"ADMIN", "SALES_MANAGER"}
        return request.method in SAFE_METHODS


def visible_tasks(user):
    tasks = FeedbackTask.objects.filter(lead__deleted_at__isnull=True).annotate(
        live_branch=Lower(Trim(Case(When(service_event__isnull=False, then=F("service_event__request__branch")), default=F("lead__branch"), output_field=CharField()))))
    if user.role in {"ADMIN", "CEO"}:
        return tasks
    if user.role == "FEEDBACK":
        return tasks.filter(assigned_to=user)
    branch = branch_key(user.location)
    if not branch:
        return tasks.none()
    if user.role == "SALES_MANAGER":
        return tasks.filter(Q(status="OPEN", live_branch=branch) | (~Q(status="OPEN") & Q(branch=branch)))
    return tasks.none()
