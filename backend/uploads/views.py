from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.permissions import IsAdmin
from leads.models import Lead, LeadAudit
from leads.serializers import validate_configured_choice
from .models import UploadBatch, UploadRow
from .serializers import ResolveRowsSerializer, UploadBatchSerializer, UploadRowSerializer
from .storage import upload_bytes
from .tasks import parse_upload_batch


class UploadBatchViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdmin]
    serializer_class = UploadBatchSerializer
    parser_classes = [MultiPartParser, JSONParser]

    def get_queryset(self):
        return UploadBatch.objects.order_by("-created_at")

    def create(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "A file is required."}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded.size > 10 * 1024 * 1024 or Path(uploaded.name).suffix.lower() not in {".csv", ".xlsx"}:
            return Response({"detail": "Upload a CSV or XLSX file below 10 MB."}, status=status.HTTP_400_BAD_REQUEST)
        path = f"imports/{timezone.now():%Y/%m}/{timezone.now().timestamp()}-{uploaded.name}"
        upload_bytes(path, uploaded.read(), uploaded.content_type or "application/octet-stream")
        batch = UploadBatch.objects.create(filename=uploaded.name, storage_path=path, uploaded_by=request.user)
        parse_upload_batch.delay(batch.id)
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

    def retrieve(self, request, pk=None):
        batch = self.get_object()
        payload = self.get_serializer(batch).data
        if request.query_params.get("include_rows") == "true":
            payload["rows"] = UploadRowSerializer(batch.rows.all().order_by("row_number"), many=True).data
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="resolve-duplicates")
    def resolve_duplicates(self, request, pk=None):
        batch = self.get_object()
        if batch.status != UploadBatch.Status.READY:
            return Response({"detail": "This upload is not ready for review."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ResolveRowsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = {row.id: row for row in batch.rows.all()}
        for item in serializer.validated_data["rows"]:
            if row := rows.get(item["id"]):
                row.resolution = item["resolution"]
                row.save(update_fields=["resolution"])
        batch.duplicates_found = batch.rows.filter(resolution=UploadRow.Resolution.PENDING).count()
        batch.save(update_fields=["duplicates_found"])
        return Response({"detail": "Duplicate choices saved.", "duplicates_found": batch.duplicates_found})

    @action(detail=True, methods=["post"])
    def commit(self, request, pk=None):
        batch = self.get_object()
        if batch.status != UploadBatch.Status.READY:
            return Response({"detail": "This upload is not ready to commit."}, status=status.HTTP_400_BAD_REQUEST)
        rows = list(batch.rows.select_related("duplicate_of").all())
        if any(row.resolution == UploadRow.Resolution.PENDING for row in rows):
            return Response({"detail": "Resolve every duplicate before committing."}, status=status.HTTP_400_BAD_REQUEST)
        rows = [row for row in rows if not row.validation_error and row.resolution != UploadRow.Resolution.SKIP]
        overwrite_leads = []
        new_leads = []
        for row in rows:
            data = {key: value for key, value in row.data.items() if not key.startswith("_")}
            data["enquiry_date"] = data.get("enquiry_date") or None
            validate_configured_choice(data.get("model_interest", ""), "models", "vehicle model")
            if row.duplicate_of and row.resolution == UploadRow.Resolution.OVERWRITE:
                for field in ("name", "email", "source", "source_label", "campaign", "model_interest", "city", "enquiry_date"):
                    setattr(row.duplicate_of, field, data.get(field, ""))
                overwrite_leads.append(row.duplicate_of)
            else:
                new_leads.append(Lead(phone=row.normalized_phone, duplicate_flag=bool(row.duplicate_of), **data))
        with transaction.atomic():
            if overwrite_leads:
                Lead.objects.bulk_update(overwrite_leads, ["name", "email", "source", "source_label", "campaign", "model_interest", "city", "enquiry_date"])
                LeadAudit.objects.bulk_create([LeadAudit(lead=lead, actor=request.user, event="import_overwrite") for lead in overwrite_leads])
            created_leads = Lead.objects.bulk_create(new_leads)
            LeadAudit.objects.bulk_create([LeadAudit(lead=lead, actor=request.user, event="imported") for lead in created_leads])
            batch.status = UploadBatch.Status.COMMITTED
            batch.committed_at = timezone.now()
            batch.save(update_fields=["status", "committed_at"])
        return Response({"created": len(created_leads), "overwritten": len(overwrite_leads), "skipped": batch.skipped})
