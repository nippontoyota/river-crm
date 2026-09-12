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
        return user, validated_token
