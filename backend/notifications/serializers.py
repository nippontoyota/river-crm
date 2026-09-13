from rest_framework import serializers

from .models import Notification, WhatsAppMessage


class NotificationSerializer(serializers.ModelSerializer):
    feedback_kind = serializers.CharField(source="feedback_task.kind", default=None)
    class Meta:
        model = Notification
        fields = ["id", "lead", "kind", "message", "read_at", "created_at", "feedback_task", "feedback_kind", "service_request"]


class WhatsAppAgreementSerializer(serializers.Serializer):
    agreed = serializers.BooleanField()


class WhatsAppMessageSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WhatsAppMessage
        fields = ["id", "kind", "mode", "recipient", "template", "language", "variables", "body", "status", "status_label", "reason", "created_at", "updated_at"]
        read_only_fields = fields
