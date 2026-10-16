from base64 import urlsafe_b64decode
from binascii import Error as Base64Error

from rest_framework import serializers

from .models import Notification, PushSubscription, WhatsAppMessage


class NotificationSerializer(serializers.ModelSerializer):
    feedback_kind = serializers.CharField(source="feedback_task.kind", default=None)
    class Meta:
        model = Notification
        fields = ["id", "lead", "kind", "message", "read_at", "created_at", "feedback_task", "feedback_kind", "service_request"]


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2048)
    keys = serializers.DictField(child=serializers.CharField(), write_only=True)

    def validate_endpoint(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("A secure push endpoint is required.")
        return value

    def validate_keys(self, value):
        p256dh = value.get("p256dh", "")
        auth = value.get("auth", "")
        try:
            public_key = urlsafe_b64decode(p256dh + "=" * (-len(p256dh) % 4))
            auth_secret = urlsafe_b64decode(auth + "=" * (-len(auth) % 4))
        except (Base64Error, ValueError):
            public_key = auth_secret = b""
        if len(public_key) != 65 or public_key[:1] != b"\x04" or len(auth_secret) != 16:
            raise serializers.ValidationError("The browser push keys are invalid.")
        return {"p256dh": p256dh, "auth": auth}

    def save(self, **kwargs):
        keys = self.validated_data["keys"]
        subscription, _ = PushSubscription.objects.update_or_create(
            endpoint=self.validated_data["endpoint"],
            defaults={
                "user": kwargs["user"],
                "p256dh": keys["p256dh"],
                "auth": keys["auth"],
                "user_agent": kwargs.get("user_agent", "")[:500],
            },
        )
        return subscription


class WhatsAppAgreementSerializer(serializers.Serializer):
    agreed = serializers.BooleanField()


class WhatsAppMessageSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WhatsAppMessage
        fields = ["id", "kind", "mode", "recipient", "template", "language", "variables", "body", "status", "status_label", "reason", "created_at", "updated_at"]
        read_only_fields = fields
