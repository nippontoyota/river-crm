import uuid

from django.conf import settings
from django.db import models


class Complaint(models.Model):
    class Category(models.TextChoices):
        SERVICE_DELAY = "SERVICE_DELAY", "Service Delay"
        PRODUCT_DEFECT = "PRODUCT_DEFECT", "Product Defect"
        DELIVERY_ISSUE = "DELIVERY_ISSUE", "Delivery Issue"
        BILLING_FINANCE = "BILLING_FINANCE", "Billing / Finance"
        AFTER_SALES = "AFTER_SALES", "After-Sales"
        STAFF_BEHAVIOUR = "STAFF_BEHAVIOUR", "Staff Behaviour"
        WARRANTY = "WARRANTY", "Warranty"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        ESCALATED = "ESCALATED", "Escalated"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Source(models.TextChoices):
        PHONE = "PHONE", "Phone"
        EMAIL = "EMAIL", "Email"
        WALKIN = "WALKIN", "Walk-in"
        SOCIAL_MEDIA = "SOCIAL_MEDIA", "Social Media"
        OTHER = "OTHER", "Other"

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    ticket_number = models.CharField(max_length=20, unique=True, editable=False)
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=10, db_index=True)
    customer_email = models.EmailField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN, db_index=True)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    model_interest = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=120, blank=True, default="")
    source = models.CharField(max_length=15, choices=Source.choices, default=Source.PHONE)
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="logged_complaints"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_complaints"
    )
    related_lead = models.ForeignKey(
        "leads.Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["logged_by", "status"]),
            models.Index(fields=["category", "created_at"]),
            models.Index(fields=["priority", "status"]),
        ]

    def __str__(self):
        return f"{self.ticket_number} — {self.subject}"

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            last = Complaint.objects.order_by("-id").values_list("id", flat=True).first()
            next_id = (last or 0) + 1
            self.ticket_number = f"CMP-{next_id:05d}"
        super().save(*args, **kwargs)


class ComplaintNote(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="complaint_notes")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.complaint.ticket_number} by {self.author}"
