from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    def enforce_csrf(self, request):
        check = CSRFCheck(lambda _: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f"CSRF failed: {reason}")

    def authenticate(self, request):
        header = self.get_header(request)
        raw_token = self.get_raw_token(header) if header else request.COOKIES.get("river_access")
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token)
        if not header:
            self.enforce_csrf(request)
        user = self.get_user(validated_token)
        if user.role == "CEO" and request.method not in {"GET", "HEAD", "OPTIONS"} and request.path != "/api/auth/logout/":
            raise exceptions.PermissionDenied("CEO access is read-only.")
        if user.role == "SERVICE" and not service_path_allowed(request):
            raise exceptions.PermissionDenied("Service accounts can only access their service workspace.")
        if user.role == "META_UPLOADER" and not meta_uploader_path_allowed(request):
            raise exceptions.PermissionDenied("Meta uploader accounts can only access bulk lead uploads.")
        return user, validated_token


def service_path_allowed(request):
    return request.path.startswith(("/api/vehicles/", "/api/service-requests/", "/api/notifications/")) or request.path in {"/api/auth/me/", "/api/auth/logout/", "/api/auth/csrf/"} or (request.path == "/api/system-config/" and request.method in {"GET", "HEAD", "OPTIONS"})


def meta_uploader_path_allowed(request):
    return request.path.startswith("/api/uploads/") or request.path in {"/api/auth/me/", "/api/auth/logout/", "/api/auth/csrf/"}
