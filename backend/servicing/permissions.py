from rest_framework.permissions import BasePermission, SAFE_METHODS

from leads.models import Lead
from .models import ServiceRequest


def visible_leads(user):
    leads = Lead.objects.filter(deleted_at__isnull=True)
    if user.role == "ADMIN":
        return leads
    if user.role == "CRE":
        return leads.filter(assigned_so=user)
    if user.role == "SO":
        return leads.filter(assigned_ps=user)
    return leads.none()


def visible_requests(user):
    rows = ServiceRequest.objects.all()
    if user.role in {"ADMIN", "CEO"}:
        return rows
    if user.role == "CRE":
        return rows.filter(created_by=user)
    if user.role == "SERVICE" and user.location.strip():
        return rows.filter(branch__iexact=user.location.strip()).exclude(status="RECORDED")
    if user.role == "SO":
        return rows.filter(vehicle__related_lead__in=visible_leads(user))
    return rows.none()


class ServicePermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or user.deleted_at:
            return False
        if user.role not in {"ADMIN", "CEO", "CRE", "SERVICE", "SO"}:
            return False
        if user.role == "SERVICE" and not user.location.strip():
            return False
        if user.role in {"CEO", "SO"}:
            return request.method in SAFE_METHODS
        return True


class VehiclePermission(ServicePermission):
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated and request.user.role == "SO":
            return bool(request.user.is_active and not request.user.deleted_at and view.action in {"list", "retrieve", "create"})
        return super().has_permission(request, view)
