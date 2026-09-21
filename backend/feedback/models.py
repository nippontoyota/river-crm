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
        SVC = "SVC", "Service feedback"
        GEN = "GEN", "Requested feedback"

    class Origin(models.TextChoices):
        AUTOMATIC = "AUTOMATIC", "Automatic"
        MANUAL = "MANUAL", "Requested feedback"
        HISTORICAL = "HISTORICAL", "Historical catch-up"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        COMPLETED = "COMPLETED", "Completed"
        UNREACHABLE = "UNREACHABLE", "Unreachable"
        DECLINED = "DECLINED", "Declined"
        INVALID_NUMBER = "INVALID_NUMBER", "Invalid number"
        CANCELLED = "CANCELLED", "Cancelled"

    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.PROTECT, related_name="feedback_tasks")
    source_audit = models.ForeignKey("leads.LeadAudit", null=True, blank=True, on_delete=models.PROTECT)
    service_event = models.OneToOneField("servicing.ServiceEvent", null=True, blank=True, on_delete=models.PROTECT, related_name="feedback_task")
    manual_request = models.OneToOneField("feedback.FeedbackRequest", null=True, blank=True, on_delete=models.PROTECT, related_name="task")
    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.AUTOMATIC)
    cancellation_reason = models.TextField(blank=True)
    questionnaire_version = models.PositiveSmallIntegerField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    satisfaction = models.PositiveSmallIntegerField(null=True, blank=True)
    further_help = models.BooleanField(default=False)
    help_details = models.TextField(blank=True)
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
        constraints = [
            models.UniqueConstraint(fields=["lead", "kind"], condition=models.Q(kind__in=["TDF", "PBF", "PSF"]), name="feedback_once_per_sales_kind"),
            models.UniqueConstraint(fields=["lead"], condition=models.Q(kind="GEN", status="OPEN"), name="feedback_one_open_request"),
            models.CheckConstraint(condition=models.Q(satisfaction__isnull=True) | models.Q(satisfaction__range=(1, 5)), name="feedback_rating_range"),
            models.CheckConstraint(condition=(
                models.Q(kind__in=["TDF", "PBF", "PSF"], lead__isnull=False, source_audit__isnull=False, service_event__isnull=True, manual_request__isnull=True)
                | models.Q(kind="SVC", service_event__isnull=False, lead__isnull=True, source_audit__isnull=True, manual_request__isnull=True)
                | models.Q(kind="GEN", lead__isnull=False, manual_request__isnull=False, source_audit__isnull=True, service_event__isnull=True)
            ), name="feedback_valid_source"),
        ]
        indexes = [models.Index(fields=["assigned_to", "status", "next_call_at"])]

    @property
    def source_branch(self):
        return self.service_event.request.branch if self.service_event_id else self.lead.branch

    @property
    def customer(self):
        return self.service_event.request.customer_snapshot.get("customer_name", "") if self.service_event_id else self.lead.name

    @property
    def phone(self):
        return self.service_event.request.customer_snapshot.get("customer_phone", "") if self.service_event_id else self.lead.phone

    @property
    def model(self):
        return self.service_event.request.vehicle_snapshot.get("model", "") if self.service_event_id else self.lead.model_interest


class FeedbackRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    lead = models.ForeignKey("leads.Lead", on_delete=models.PROTECT, related_name="feedback_requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedback_requests")
    reason = models.TextField()
    preferred_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="reviewed_feedback_requests")
    reviewed_at = models.DateTimeField(null=True)
    review_notes = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead"], condition=models.Q(status="PENDING"), name="feedback_one_pending_request")]


class FeedbackIssue(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"

    task = models.OneToOneField(FeedbackTask, on_delete=models.PROTECT, related_name="issue")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    reason = models.TextField()
    complaint = models.OneToOneField("complaints.Complaint", null=True, blank=True, on_delete=models.PROTECT, related_name="feedback_issue")
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="acknowledged_feedback_issues")
    acknowledged_at = models.DateTimeField(null=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="resolved_feedback_issues")
    resolved_at = models.DateTimeField(null=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class FeedbackIssueEvent(models.Model):
    issue = models.ForeignKey(FeedbackIssue, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=FeedbackIssue.Status.choices)
    note = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]


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
