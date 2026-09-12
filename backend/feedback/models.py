from django.conf import settings
from django.db import models
from django.utils import timezone


class FeedbackState(models.Model):
    """The activation boundary also serializes feedback allocation and mutations."""
    activated_at = models.DateTimeField(default=timezone.now)


class FeedbackTask(models.Model):
    class Kind(models.TextChoices):
        TDF = "TDF", "Test drive feedback"
        PBF = "PBF", "Post booking feedback"
        PSF = "PSF", "Post sales feedback"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        COMPLETED = "COMPLETED", "Completed"
        UNREACHABLE = "UNREACHABLE", "Unreachable"
        DECLINED = "DECLINED", "Declined"
        INVALID_NUMBER = "INVALID_NUMBER", "Invalid number"

    lead = models.ForeignKey("leads.Lead", on_delete=models.PROTECT, related_name="feedback_tasks")
    source_audit = models.ForeignKey("leads.LeadAudit", on_delete=models.PROTECT)
    kind = models.CharField(max_length=3, choices=Kind.choices)
    branch = models.CharField(max_length=120, blank=True, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="feedback_tasks")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    occurred_at = models.DateTimeField()
    original_due_at = models.DateTimeField(db_index=True)
    next_call_at = models.DateTimeField(db_index=True)
    unsuccessful_attempts = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    on_time = models.BooleanField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead", "kind"], name="feedback_once_per_lead_kind")]
        indexes = [models.Index(fields=["assigned_to", "status", "next_call_at"])]


class FeedbackAttempt(models.Model):
    class Outcome(models.TextChoices):
        COLLECTED = "COLLECTED", "Feedback collected"
        NO_ANSWER = "NO_ANSWER", "No answer"
        BUSY = "BUSY", "Busy"
        SWITCHED_OFF = "SWITCHED_OFF", "Switched off"
        CALLBACK = "CALLBACK", "Customer requested callback"
        DECLINED = "DECLINED", "Declined"
        INVALID_NUMBER = "INVALID_NUMBER", "Invalid number"

    task = models.ForeignKey(FeedbackTask, on_delete=models.PROTECT, related_name="attempts")
    caller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    branch = models.CharField(max_length=120, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    notes = models.TextField(blank=True)
    scheduled_for = models.DateTimeField()
    callback_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class FeedbackAssignment(models.Model):
    task = models.ForeignKey(FeedbackTask, on_delete=models.PROTECT, related_name="assignments")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="feedback_assignment_actions")
    previous_owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="previous_feedback_assignments")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="feedback_assignments")
    previous_branch = models.CharField(max_length=120, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
