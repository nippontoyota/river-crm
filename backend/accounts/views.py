from django.conf import settings
from django.contrib.auth import get_user_model
from django.middleware.csrf import get_token
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .permissions import IsAdmin
from .serializers import TeamMemberSerializer, UserSerializer, LoginSerializer


def set_auth_cookies(response, refresh):
    cookie_settings = {"httponly": True, "secure": not settings.DEBUG, "samesite": "Lax" if settings.DEBUG else "None"}
    response.set_cookie("river_access", str(refresh.access_token), max_age=900, **cookie_settings)
    response.set_cookie("river_refresh", str(refresh), max_age=604800, **cookie_settings)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh = RefreshToken.for_user(serializer.validated_data["user"])
        response = Response({"user": UserSerializer(serializer.validated_data["user"]).data})
        set_auth_cookies(response, refresh)
        return response


class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        token = request.COOKIES.get("river_refresh")
        if not token:
            return Response({"detail": "Refresh token missing."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(token)
            user = get_user_model().objects.get(id=refresh["user_id"], is_active=True)
            refresh.blacklist()
            refresh = RefreshToken.for_user(user)
        except Exception:
            return Response({"detail": "Refresh token invalid."}, status=status.HTTP_401_UNAUTHORIZED)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        set_auth_cookies(response, refresh)
        return response


class LogoutView(APIView):
    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie("river_access")
        response.delete_cookie("river_refresh")
        return response


class MeView(APIView):
    def get(self, request):
        return Response({"user": UserSerializer(request.user).data})


class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RoleUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = TeamMemberSerializer
    role = None

    def get_queryset(self):
        return get_user_model().objects.filter(role=self.role).order_by("first_name", "email")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": self.role}

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        active = user.assigned_leads if self.role == get_user_model().Role.CRE else user.ps_leads
        if active.filter(deleted_at__isnull=True).exists():
            return Response({"detail": "Reassign this user's active leads before deactivation."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CREViewSet(RoleUserViewSet):
    role = get_user_model().Role.CRE


class SalesOfficerViewSet(RoleUserViewSet):
    role = get_user_model().Role.SALES_OFFICER

    def get_permissions(self):
        if self.action == "list":
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_admin:
            queryset = queryset.filter(is_active=True)
        if location := self.request.query_params.get("location"):
            queryset = queryset.filter(location__iexact=location.strip())
        return queryset

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = TeamMemberSerializer
    queryset = get_user_model().objects.all().order_by("first_name", "email")

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        active = user.assigned_leads.all() | user.ps_leads.all()
        if active.filter(deleted_at__isnull=True).exists():
            return Response({"detail": "Reassign this user's active leads before deactivation."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

