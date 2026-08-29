from rest_framework.permissions import BasePermission

from accounts.models import User


class ComplaintPermission(BasePermission):
    message = "Complaints are logged by CRE and resolved by the complaints department."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_admin:
            return view.action in {"list", "retrieve"}
        if request.user.role == User.Role.CRE:
            return view.action in {"list", "retrieve", "create"}
        if request.user.role == User.Role.COMPLAINTS:
            return view.action in {"list", "retrieve", "update", "partial_update", "add_note"}
        return False


class ComplaintAnalyticsPermission(BasePermission):
    message = "Complaint analytics are available to admins and complaints department users."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_admin or request.user.role == User.Role.COMPLAINTS)
        )
