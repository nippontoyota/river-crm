from django.utils import timezone
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, mixins

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(mixins.ListModelMixin, GenericViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        from feedback.permissions import visible_tasks
        queryset = Notification.objects.filter(user=self.request.user).filter(
            Q(feedback_task__isnull=True) | Q(feedback_task__in=visible_tasks(self.request.user)))
        if self.request.query_params.get("feedback") == "true":
            queryset = queryset.filter(feedback_task__isnull=False)
        if kind := self.request.query_params.get("feedback_kind"):
            queryset = queryset.filter(feedback_task__kind=kind)
        return queryset.select_related("feedback_task").order_by("-created_at", "-id")

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
