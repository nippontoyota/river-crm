import uuid

from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    chassis_number = models.CharField(max_length=64, unique=True)
    model = models.CharField(max_length=100)
    registration_number = models.CharField(max_length=30, blank=True)
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=10)
    customer_email = models.EmailField(blank=True)
    related_lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.PROTECT, related_name="vehicles")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def customer(self):
        lead = self.related_lead
        return {"customer_name": lead.name, "customer_phone": lead.phone, "customer_email": lead.email} if lead else {
            "customer_name": self.customer_name, "customer_phone": self.customer_phone, "customer_email": self.customer_email}


class ServiceRequest(models.Model):
    class Status(models.TextChoices):
        RECORDED = "RECORDED", "Recorded"
        FORWARDED = "FORWARDED", "Incoming"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        WAITING = "WAITING", "Waiting"
        RESOLVED = "RESOLVED", "Resolved"
        CANCELLED = "CANCELLED", "Cancelled"

    class Source(models.TextChoices):
        PHONE = "PHONE", "Phone"
        WALKIN = "WALKIN", "Walk-in"
        EMAIL = "EMAIL", "Email"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="requests")
    customer_snapshot = models.JSONField(default=dict)
    vehicle_snapshot = models.JSONField(default=dict)
    issue = models.TextField()
    branch = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECORDED, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PHONE)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    odometer = models.PositiveIntegerField(null=True, blank=True)
    preferred_appointment = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_requests")
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def ticket_number(self):
        return f"SRV-{self.pk:06d}"

    class Meta:
        ordering = ["-created_at", "-id"]


class ServiceEvent(models.Model):
    request = models.ForeignKey(ServiceRequest, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=24)
    note = models.TextField(blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class VehicleEvent(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
