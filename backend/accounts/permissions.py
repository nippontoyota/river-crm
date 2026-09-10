from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = "Admin access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsAdminOrReceptionist(BasePermission):
    message = "Admin or Receptionist access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_admin or getattr(request.user, "role", None) == "RECEPTIONIST"))


class IsAdminReceptionistOrCRE(BasePermission):
    message = "Admin, Receptionist, or CE access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_admin or getattr(request.user, "role", None) in ["RECEPTIONIST", "CRE"]))


class IsSalesManager(BasePermission):
    message = "Sales Manager access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, "role", None) == "SALES_MANAGER")


class IsSalesOfficer(BasePermission):
    message = "Sales Officer access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active and not request.user.deleted_at and request.user.role == "SO")
