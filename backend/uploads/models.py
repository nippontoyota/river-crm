from django.conf import settings
from django.db import models


class UploadBatch(models.Model):
    class Status(models.TextChoices):
        PARSING = "PARSING", "Parsing"
        READY = "READY", "Ready for review"
        COMMITTED = "COMMITTED", "Committed"
        FAILED = "FAILED", "Failed"

    filename = models.CharField(max_length=255)
    storage_path = models.CharField(max_length=500)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PARSING)
    total_rows = models.PositiveIntegerField(default=0)
    parsed_ok = models.PositiveIntegerField(default=0)
    duplicates_found = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)


class UploadRow(models.Model):
    class Resolution(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SKIP = "SKIP", "Skip"
        OVERWRITE = "OVERWRITE", "Overwrite"
        IMPORT = "IMPORT", "Import as new"

    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    data = models.JSONField(default=dict)
    normalized_phone = models.CharField(max_length=10, blank=True)
    validation_error = models.CharField(max_length=255, blank=True)
    duplicate_of = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.SET_NULL)
    resolution = models.CharField(max_length=12, choices=Resolution.choices, default=Resolution.IMPORT)
