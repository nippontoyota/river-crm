from rest_framework import serializers

from .models import UploadBatch, UploadRow


class UploadBatchSerializer(serializers.ModelSerializer):
    crm_duplicates_found = serializers.SerializerMethodField()
    file_duplicates_found = serializers.SerializerMethodField()
    removed_duplicates = serializers.SerializerMethodField()
    pending_duplicates = serializers.SerializerMethodField()

    class Meta:
        model = UploadBatch
        fields = ["id", "filename", "status", "total_rows", "parsed_ok", "duplicates_found", "crm_duplicates_found", "file_duplicates_found", "removed_duplicates", "pending_duplicates", "skipped", "error_message", "created_at", "committed_at"]

    def get_crm_duplicates_found(self, batch):
        return batch.rows.filter(duplicate_of__isnull=False).count()

    def get_file_duplicates_found(self, batch):
        return sum(1 for row in batch.rows.all() if row.data.get("_duplicate_type") == "FILE")

    def get_removed_duplicates(self, batch):
        return sum(1 for row in batch.rows.all() if row.resolution == UploadRow.Resolution.SKIP and row.data.get("_duplicate_type"))

    def get_pending_duplicates(self, batch):
        return batch.rows.filter(resolution=UploadRow.Resolution.PENDING).count()


class UploadRowSerializer(serializers.ModelSerializer):
    existing_name = serializers.SerializerMethodField()
    existing_status = serializers.SerializerMethodField()
    duplicate_type = serializers.SerializerMethodField()

    class Meta:
        model = UploadRow
        fields = ["id", "row_number", "data", "normalized_phone", "validation_error", "duplicate_of", "existing_name", "existing_status", "duplicate_type", "resolution"]

    def get_existing_name(self, row):
        if row.duplicate_of:
            return row.duplicate_of.name
        return row.data.get("_duplicate_label", "")

    def get_existing_status(self, row):
        if row.duplicate_of:
            return row.duplicate_of.status
        return "Same upload" if row.data.get("_duplicate_type") == "FILE" else ""

    def get_duplicate_type(self, row):
        if row.duplicate_of:
            return "CRM"
        return row.data.get("_duplicate_type", "")


class ResolveRowsSerializer(serializers.Serializer):
    rows = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate_rows(self, rows):
        valid = {choice for choice, _ in UploadRow.Resolution.choices}
        for row in rows:
            if "id" not in row or row.get("resolution") not in valid:
                raise serializers.ValidationError("Each row needs an id and valid resolution.")
        return rows
