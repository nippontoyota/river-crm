from django.conf import settings
from django.db.models import Count, Q
from rest_framework import serializers

from .models import UploadBatch, UploadRow
from .tasks import DUPLICATE_ROWS, GROUP_SAMPLE_SIZE, MAX_ROWS


class UploadBatchSerializer(serializers.ModelSerializer):
    processing_mode = serializers.SerializerMethodField()
    validation_errors_found = serializers.IntegerField(read_only=True)
    crm_duplicates_found = serializers.IntegerField(read_only=True)
    file_duplicates_found = serializers.IntegerField(read_only=True)
    intake_duplicates_found = serializers.IntegerField(read_only=True)
    removed_duplicates = serializers.IntegerField(read_only=True)
    pending_duplicates = serializers.IntegerField(read_only=True)

    class Meta:
        model = UploadBatch
        fields = ["id", "filename", "status", "total_rows", "parsed_ok", "duplicates_found", "crm_duplicates_found", "file_duplicates_found", "intake_duplicates_found", "removed_duplicates", "pending_duplicates", "skipped", "error_message", "created_at", "committed_at", "mapping_version", "original_deleted_at", "validation_errors_found", "processing_mode"]

    def get_processing_mode(self, batch) -> str:
        return settings.INTAKE_EXECUTION_MODE

    def to_representation(self, batch):
        counts = batch.rows.aggregate(
            validation_errors_found=Count('pk', filter=~Q(validation_error='')),
            crm_duplicates_found=Count('pk', filter=Q(duplicate_of__isnull=False)),
            file_duplicates_found=Count('pk', filter=Q(data___file_rows__0__isnull=False)),
            intake_duplicates_found=Count('pk', filter=Q(data___duplicate_type='INTAKE')),
            removed_duplicates=Count('pk', filter=Q(resolution='SKIP') & DUPLICATE_ROWS),
            pending_duplicates=Count('pk', filter=Q(resolution='PENDING')),
        )
        return {**super().to_representation(batch), **counts}


class UploadRowSerializer(serializers.ModelSerializer):
    existing_name = serializers.SerializerMethodField()
    existing_status = serializers.SerializerMethodField()
    duplicate_type = serializers.SerializerMethodField()
    file_rows = serializers.SerializerMethodField()
    file_row_count = serializers.SerializerMethodField()

    class Meta:
        model = UploadRow
        fields = ["id", "row_number", "data", "normalized_phone", "validation_error", "duplicate_of", "existing_name", "existing_status", "duplicate_type", "file_rows", "file_row_count", "resolution", "validation_errors"]

    def get_file_rows(self, row):
        return row.data.get("_file_rows", [])[:GROUP_SAMPLE_SIZE]

    def get_file_row_count(self, row):
        return row.data.get('_file_row_count', len(row.data.get('_file_rows', [])))

    def to_representation(self, row):
        result = super().to_representation(row)
        result['data'] = {key: value for key, value in row.data.items() if not key.startswith('_')}
        return result

    def get_existing_name(self, row):
        if row.duplicate_of:
            return row.duplicate_of.name
        if row.data.get('_duplicate_type') == 'FILE':
            return 'Repeated in this file'
        return row.data.get("_duplicate_label", "")

    def get_existing_status(self, row):
        if row.duplicate_of:
            return row.duplicate_of.status
        return "Same upload" if row.data.get("_duplicate_type") == "FILE" else ""

    def get_duplicate_type(self, row):
        if row.duplicate_of:
            return "CRM"
        return row.data.get("_duplicate_type", "")


class RowResolutionSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    resolution = serializers.ChoiceField(choices=["APPROVE", "SKIP"])


class ResolveRowsSerializer(serializers.Serializer):
    rows = RowResolutionSerializer(many=True, allow_empty=False, max_length=MAX_ROWS)
