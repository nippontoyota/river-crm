import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Connection(models.Model):
    class Origin(models.TextChoices):
        WEBSITE = 'WEBSITE', 'Website'
        META = 'META', 'Meta'

    name = models.CharField(max_length=160)
    origin = models.CharField(max_length=10, choices=Origin.choices)
    source = models.CharField(max_length=100)
    secret_ref = models.SlugField(max_length=100)
    activated_at = models.DateTimeField(default=timezone.now)
    enabled = models.BooleanField(default=False)
    paused_reason = models.CharField(max_length=80, blank=True)
    last_receipt_at = models.DateTimeField(null=True, blank=True)
    last_import_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    rate_window = models.DateTimeField(null=True, blank=True)
    rate_count = models.PositiveIntegerField(default=0)


class IntakeForm(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, related_name='forms')
    name = models.CharField(max_length=160)
    external_id = models.CharField(max_length=160)
    page_id = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=False)
    activated_at = models.DateTimeField(default=timezone.now)
    checkpoint = models.DateTimeField(null=True, blank=True)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    reconcile_lease_until = models.DateTimeField(null=True, blank=True)
    reconcile_error = models.CharField(max_length=80, blank=True)
    fetch_requested_at = models.DateTimeField(null=True, blank=True)
    reconcile_start = models.DateTimeField(null=True, blank=True)
    reconcile_end = models.DateTimeField(null=True, blank=True)
    reconcile_cursor = models.TextField(blank=True)

    @property
    def fetch_status(self) -> str:
        if self.reconcile_error:
            return 'error'
        if self.reconcile_lease_until and self.reconcile_lease_until > timezone.now():
            return 'running'
        if self.fetch_requested_at:
            return 'queued'
        return 'completed' if self.last_reconciled_at else 'idle'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['connection', 'external_id'], name='intake_connection_form_unique'),
            models.UniqueConstraint(fields=['page_id', 'external_id'], condition=~models.Q(page_id=''), name='intake_meta_pair_unique'),
        ]


class MappingVersion(models.Model):
    form = models.ForeignKey(IntakeForm, null=True, blank=True, on_delete=models.PROTECT, related_name='mappings')
    template_name = models.CharField(max_length=160, blank=True)
    version = models.PositiveIntegerField()
    rules = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(models.Q(form__isnull=False, template_name='') | (models.Q(form__isnull=True) & ~models.Q(template_name=''))), name='intake_mapping_scope'),
            models.UniqueConstraint(fields=['form', 'version'], condition=models.Q(form__isnull=False), name='intake_form_version_unique'),
            models.UniqueConstraint(fields=['template_name', 'version'], condition=models.Q(form__isnull=True), name='intake_template_version_unique'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Mapping versions are immutable. Create a new version.')
        return super().save(*args, **kwargs)


class Submission(models.Model):
    class State(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received'
        PROCESSING = 'PROCESSING', 'Processing'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'
        IMPORTED = 'IMPORTED', 'Imported'
        LINKED = 'LINKED', 'Linked'
        FAILED = 'FAILED', 'Failed'
        DISMISSED = 'DISMISSED', 'Dismissed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, related_name='submissions')
    form = models.ForeignKey(IntakeForm, on_delete=models.PROTECT, related_name='submissions')
    external_id = models.CharField(max_length=160)
    # Meta identity has no form component; website IDs are scoped to a form.
    identity = models.CharField(max_length=330)
    fingerprint = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=100)
    submitted_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=list)
    ignored_labels = models.JSONField(default=list)
    answers_expired = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(null=True, blank=True)
    mapped_values = models.JSONField(default=dict)
    corrections = models.JSONField(default=dict)
    campaign_name = models.CharField(max_length=160, blank=True)
    attribution = models.JSONField(default=dict)
    mapping_version = models.ForeignKey(MappingVersion, null=True, blank=True, on_delete=models.PROTECT)
    normalized_phone = models.CharField(max_length=10, blank=True, db_index=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.RECEIVED, db_index=True)
    errors = models.JSONField(default=dict)
    review_reason = models.CharField(max_length=40, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, null=True, blank=True, db_index=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lead = models.ForeignKey('leads.Lead', null=True, blank=True, on_delete=models.PROTECT, related_name='intake_submissions')
    blocked_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection', 'identity'], name='intake_external_identity_unique')]
        indexes = [models.Index(fields=['state', 'next_attempt_at'])]


class IntakeAudit(models.Model):
    submission = models.ForeignKey(Submission, null=True, blank=True, on_delete=models.PROTECT, related_name='history')
    connection = models.ForeignKey(Connection, null=True, blank=True, on_delete=models.PROTECT)
    mapping_version = models.ForeignKey(MappingVersion, null=True, blank=True, on_delete=models.PROTECT)
    lead = models.ForeignKey('leads.Lead', null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)


class Heartbeat(models.Model):
    name = models.CharField(max_length=30, primary_key=True)
    seen_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
