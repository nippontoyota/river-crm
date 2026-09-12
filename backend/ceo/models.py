import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Milestone(models.Model):
    lead = models.ForeignKey("leads.Lead", on_delete=models.PROTECT, related_name="milestones")
    kind = models.CharField(max_length=1, choices=[(value, label) for value, label in [("E", "Enquiry"), ("T", "Test drive"), ("B", "Booking"), ("R", "Retail")]])
    occurred_on = models.DateField(null=True, db_index=True)
    occurred_at = models.DateTimeField(null=True)
    branch = models.CharField(max_length=120, blank=True, db_index=True)
    rto = models.CharField(max_length=5, blank=True)
    source = models.CharField(max_length=100, blank=True)
    campaign = models.CharField(max_length=160, blank=True)
    activity = models.CharField(max_length=160, blank=True)
    sub_activity = models.CharField(max_length=160, blank=True)
    model_interest = models.CharField(max_length=100, blank=True)
    cre = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="ceo_cre_milestones")
    so = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="ceo_so_milestones")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="ceo_milestones")
    provenance = models.CharField(max_length=20, default="recorded")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead", "kind"], name="ceo_first_lead_milestone")]
        indexes = [models.Index(fields=["kind", "occurred_on", "branch"])]


class OperationEvent(models.Model):
    lead = models.ForeignKey("leads.Lead", null=True, on_delete=models.PROTECT, related_name="operation_events")
    complaint = models.ForeignKey("complaints.Complaint", null=True, on_delete=models.PROTECT, related_name="operation_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="operation_events")
    kind = models.CharField(max_length=60, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    source_key = models.CharField(max_length=100, unique=True)
    branch = models.CharField(max_length=120, blank=True, db_index=True)
    snapshot = models.JSONField(default=dict)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    provenance = models.CharField(max_length=20, default="recorded")

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["lead", "occurred_at"]), models.Index(fields=["actor", "occurred_at"])]


class SalesTarget(models.Model):
    month = models.DateField()
    branch = models.CharField(max_length=120)
    so = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_targets")
    enquiries = models.PositiveIntegerField(default=0)
    test_drives = models.PositiveIntegerField(default=0)
    bookings = models.PositiveIntegerField(default=0)
    retails = models.PositiveIntegerField(default=0)
    retail_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["month", "branch", "so"], condition=Q(so__isnull=False), name="ceo_so_target_unique"),
            models.UniqueConstraint(fields=["month", "branch"], condition=Q(so__isnull=True), name="ceo_branch_target_unique"),
            models.CheckConstraint(condition=Q(retail_value__gte=0), name="ceo_positive_target_value"),
        ]


class TargetRevision(models.Model):
    target = models.ForeignKey(SalesTarget, on_delete=models.PROTECT, related_name="revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class SaleAccount(models.Model):
    lead = models.OneToOneField("leads.Lead", on_delete=models.PROTECT, related_name="sale_account")
    agreed_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    retail_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    confirmed_on = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(agreed_amount__gte=0) | Q(agreed_amount__isnull=True), name="ceo_positive_agreed"), models.CheckConstraint(condition=Q(retail_amount__gte=0) | Q(retail_amount__isnull=True), name="ceo_positive_retail")]


class FinancialEntry(models.Model):
    account = models.ForeignKey(SaleAccount, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=12, choices=[("PAYMENT", "Payment"), ("REFUND", "Refund"), ("REVERSAL", "Reversal"), ("VALUATION", "Sale value revision")])
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    occurred_on = models.DateField(db_index=True)
    method = models.CharField(max_length=20, blank=True, choices=[("", "Not applicable"), ("CASH", "Cash"), ("BANK", "Bank transfer"), ("UPI", "UPI"), ("CARD", "Card"), ("FINANCE", "Finance disbursement"), ("OTHER", "Other")])
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=500)
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal")
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    branch = models.CharField(max_length=120, blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]
