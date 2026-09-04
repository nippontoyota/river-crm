from django.conf import settings
from django.contrib.auth import get_user_model
from django.middleware.csrf import get_token
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .permissions import IsAdmin
from .serializers import TeamMemberSerializer, UserSerializer, LoginSerializer
from .models import UserLifecycleEvent
from .offboarding import enable_user, offboard_user, offboarding_impact


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


class UserLifecycleHistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, user_id):
        user = get_user_model().objects.filter(pk=user_id, role__in=[get_user_model().Role.CRE, get_user_model().Role.SALES_OFFICER]).first()
        if not user:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        events = [{
            "action": event.action,
            "reason": event.reason,
            "actor": (event.actor.get_full_name() or event.actor.email) if event.actor else "System",
            "summary": event.summary,
            "created_at": event.created_at,
        } for event in user.lifecycle_events.select_related("actor")]
        return Response({"id": user.id, "name": user.get_full_name() or user.email, "lifecycle_status": user.lifecycle_status, "account_history": events})


class RoleUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = TeamMemberSerializer
    role = None

    def get_queryset(self):
        return get_user_model().objects.filter(role=self.role, is_active=True, deleted_at__isnull=True).order_by("first_name", "email")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": self.role}

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Use the explicit Disable or Permanent Delete action."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


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
    queryset = get_user_model().objects.filter(deleted_at__isnull=True).order_by("first_name", "email")

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Use the explicit Disable or Permanent Delete action."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["get"], url_path="offboarding-impact")
    def impact(self, request, pk=None):
        return Response(offboarding_impact(self.get_object()))

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        summary = offboard_user(
            self.get_object().id,
            request.user,
            UserLifecycleEvent.Action.DISABLED,
            request.data.get("impact_version", ""),
            request.data.get("routes", []),
        )
        return Response({"status": "DISABLED", "summary": summary})

    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        user = enable_user(self.get_object().id, request.user)
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"], url_path="permanent-delete")
    def permanent_delete(self, request, pk=None):
        summary = offboard_user(
            self.get_object().id,
            request.user,
            UserLifecycleEvent.Action.DELETED,
            request.data.get("impact_version", ""),
            request.data.get("routes", []),
            request.data.get("reason", ""),
        )
        return Response({"status": "DELETED", "summary": summary})
