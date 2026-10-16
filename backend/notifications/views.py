from django.conf import settings
from django.utils import timezone
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, mixins

from accounts.models import User
from .models import Notification, PushSubscription
from .serializers import NotificationSerializer, PushSubscriptionSerializer


class NotificationViewSet(mixins.ListModelMixin, GenericViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        from feedback.permissions import visible_tasks
        queryset = Notification.objects.filter(user=self.request.user).filter(
            Q(feedback_task__isnull=True) | Q(feedback_task__in=visible_tasks(self.request.user)))
        from servicing.permissions import visible_requests
        queryset = queryset.filter(Q(service_request__isnull=True) | Q(service_request__in=visible_requests(self.request.user)))
        if self.request.user.role == "SERVICE" or self.request.query_params.get("service") == "true":
            queryset = queryset.filter(service_request__isnull=False)
        if self.request.query_params.get("feedback") == "true":
            queryset = queryset.filter(feedback_task__isnull=False)
        if kind := self.request.query_params.get("kind"):
            queryset = queryset.filter(kind=kind) if kind in Notification.Kind.values else queryset.none()
        if kind := self.request.query_params.get("feedback_kind"):
            queryset = queryset.filter(feedback_task__kind=kind)
        return queryset.select_related("feedback_task").order_by("-created_at", "-id")

    def require_ps(self):
        if self.request.user.role != User.Role.SALES_OFFICER:
            raise PermissionDenied("Phone lead alerts are only available to PS/SO users.")

    @action(detail=False, methods=["get"], url_path="push-config")
    def push_config(self, request):
        self.require_ps()
        enabled = bool(settings.WEB_PUSH_VAPID_PUBLIC_KEY and settings.WEB_PUSH_VAPID_PRIVATE_KEY and settings.WEB_PUSH_VAPID_SUBJECT)
        return Response({
            "enabled": enabled,
            "public_key": settings.WEB_PUSH_VAPID_PUBLIC_KEY if enabled else "",
            "subscribed": PushSubscription.objects.filter(user=request.user).exists(),
        })

    @action(detail=False, methods=["post"], url_path="push-subscribe")
    def push_subscribe(self, request):
        self.require_ps()
        if not (settings.WEB_PUSH_VAPID_PUBLIC_KEY and settings.WEB_PUSH_VAPID_PRIVATE_KEY and settings.WEB_PUSH_VAPID_SUBJECT):
            raise ValidationError({"detail": "Phone push notifications are not configured."})
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, user_agent=request.headers.get("User-Agent", ""))
        return Response({"subscribed": True}, status=201)

    @action(detail=False, methods=["post"], url_path="push-unsubscribe")
    def push_unsubscribe(self, request):
        self.require_ps()
        endpoint = request.data.get("endpoint", "")
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response(status=204)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=False, methods=["post"])
    def mark_read(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(status=204)
