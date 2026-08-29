from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        ASSIGNMENT = "ASSIGNMENT", "Assignment"
        FOLLOW_UP = "FOLLOW_UP", "Follow-up"
        OVERDUE = "OVERDUE", "Overdue"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.CharField(max_length=280)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
