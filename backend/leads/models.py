import uuid

from django.conf import settings
from django.db import models


class Lead(models.Model):
    class Status(models.TextChoices):
        FRESH = "FRESH", "Fresh"
        RNR = "RNR", "RNR"
        SWITCHED_OFF = "SWITCHED_OFF", "Switched off"
        CALLBACK = "CALLBACK", "Callback Scheduled"
        PENDING = "PENDING", "Pending"
        QUALIFIED = "QUALIFIED", "Qualified"
        UNQUALIFIED = "UNQUALIFIED", "Unqualified"
        WALKIN = "WALKIN", "Walk-in Booked"
        WON = "WON", "Won"
        LOST = "LOST", "Lost"

    class Source(models.TextChoices):
        META = "META", "Meta Ads"
        WEBSITE = "WEBSITE", "Website"
        CARWALE = "CARWALE", "CarWale"
        WALKIN = "WALKIN", "Walk-in"
        CAMPAIGN = "CAMPAIGN", "Campaign"
        OTHER = "OTHER", "Other"
        UNKNOWN = "UNKNOWN", "Unknown"

    class Category(models.TextChoices):
        HOT = "HOT", "Hot"
        WARM = "WARM", "Warm"
        COLD = "COLD", "Cold"

    class SalesOutcome(models.TextChoices):
        PENDING = "PENDING", "Pending"
        BOOKED = "BOOKED", "Booked"
        RETAILED = "RETAILED", "Retailed"
        LOST = "LOST", "Lost"

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=10, db_index=True)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=100, default=Source.UNKNOWN)
    source_label = models.CharField(max_length=100, blank=True)
    campaign = models.CharField(max_length=160, blank=True)
    model_interest = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    profession = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    enquiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.FRESH, db_index=True)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.WARM, db_index=True)
    sales_outcome = models.CharField(max_length=12, choices=SalesOutcome.choices, default=SalesOutcome.PENDING, db_index=True)
    assigned_so = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_leads")
    assigned_ps = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="ps_leads")
    duplicate_flag = models.BooleanField(default=False)
    flagged_to_manager = models.BooleanField(default=False)
    needs_cre_reassignment = models.BooleanField(default=False, db_index=True)
    needs_so_reassignment = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["assigned_so", "status"]), models.Index(fields=["assigned_so", "category"]), models.Index(fields=["assigned_ps", "status"]), models.Index(fields=["source", "created_at"])]


class CallLog(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="call_logs")
    so = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="call_logs")
    status = models.CharField(max_length=20, choices=Lead.Status.choices)
    call_status = models.CharField(max_length=20, blank=True)
    outcome = models.CharField(max_length=30, blank=True)
    remarks = models.CharField(max_length=500, blank=True)
    other_so = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="other_so_call_logs")
    created_at = models.DateTimeField(auto_now_add=True)


class FollowUp(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="follow_ups")
    so = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="follow_ups")
    scheduled_for = models.DateTimeField(db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    reminder_held = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LeadQualification(models.Model):
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="qualification")
    variant = models.CharField(max_length=120, blank=True)
    buying_timeline = models.CharField(max_length=80, blank=True)
    finance_type = models.CharField(max_length=80, blank=True)
    trade_in = models.BooleanField(null=True, blank=True)
    test_drive = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_qualifications")
    updated_at = models.DateTimeField(auto_now=True)


class LeadAudit(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event = models.CharField(max_length=60)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class SystemConfig(models.Model):
    lists = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
