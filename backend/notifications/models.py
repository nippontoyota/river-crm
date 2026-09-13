from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        SERVICE_UPDATE = "SERVICE_UPDATE", "Service update"
        ASSIGNMENT = "ASSIGNMENT", "Assignment"
        FOLLOW_UP = "FOLLOW_UP", "Follow-up"
        OVERDUE = "OVERDUE", "Overdue"
        FEEDBACK_ASSIGNED = "FEEDBACK_ASSIGNED", "Feedback assigned"
        FEEDBACK_DUE = "FEEDBACK_DUE", "Feedback due"
        FEEDBACK_OVERDUE = "FEEDBACK_OVERDUE", "Feedback overdue"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.CASCADE)
    feedback_task = models.ForeignKey("feedback.FeedbackTask", null=True, blank=True, on_delete=models.CASCADE)
    service_request = models.ForeignKey("servicing.ServiceRequest", null=True, blank=True, on_delete=models.CASCADE)
    dedupe_key = models.CharField(max_length=120, null=True, blank=True, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.CharField(max_length=280)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WhatsAppContact(models.Model):
    lead = models.OneToOneField("leads.Lead", on_delete=models.CASCADE, related_name="whatsapp_contact")
    agreed = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="whatsapp_agreements")
    recorded_at = models.DateTimeField(null=True)
    enrolled_at = models.DateTimeField(null=True)
    last_so = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="whatsapp_contacts")


class WhatsAppMessage(models.Model):
    class Kind(models.TextChoices):
        INTRODUCTION = "INTRODUCTION", "SO introduction"
        REASSIGNMENT = "REASSIGNMENT", "SO changed"

    class Status(models.TextChoices):
        PREVIEW = "PREVIEW", "Preview only — not sent"
        SKIPPED = "SKIPPED", "Skipped"
        CANCELLED = "CANCELLED", "Cancelled — not sent"

    lead = models.ForeignKey("leads.Lead", on_delete=models.CASCADE, related_name="whatsapp_messages")
    source_audit = models.OneToOneField("leads.LeadAudit", on_delete=models.PROTECT, related_name="whatsapp_message")
    so = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="whatsapp_messages")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    mode = models.CharField(max_length=10)
    recipient = models.CharField(max_length=20, blank=True)
    template = models.CharField(max_length=100)
    language = models.CharField(max_length=20)
    variables = models.JSONField(default=dict)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    reason = models.CharField(max_length=280, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
