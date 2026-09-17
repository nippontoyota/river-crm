from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.permissions import IsAdminOrMetaUploader
from intake.mapping import validate_customer
from intake.services import publish
from leads.models import Lead, LeadAudit
from leads.phone_lock import lock_phones
from .models import UploadBatch, UploadRow
from .serializers import ResolveRowsSerializer, UploadBatchSerializer, UploadRowSerializer
from .storage import upload_bytes
from .tasks import COLUMNS, classify_rows, parse_upload_batch, refresh_counts, delete_original


class UploadBatchViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdminOrMetaUploader]
    serializer_class = UploadBatchSerializer
    parser_classes = [MultiPartParser, JSONParser]

    def get_queryset(self):
        batches = UploadBatch.objects.order_by('-created_at')
        if self.request.user.role == 'META_UPLOADER':
            batches = batches.filter(uploaded_by=self.request.user)
        return batches

    def create(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            raise ValidationError({'detail': 'A file is required.'})
        if uploaded.size > 10 * 1024 * 1024 or Path(uploaded.name).suffix.lower() not in {'.csv', '.xlsx'}:
            raise ValidationError({'detail': 'Upload a CSV or XLSX file below 10 MB.'})
        if request.data.get('mapping_version'):
            raise ValidationError({'detail': 'Bulk upload uses the fixed sample headings. Download the sample, correct your file offline, and upload it again.'})
        path = f'imports/{timezone.now():%Y/%m}/{timezone.now().timestamp()}-{uploaded.name}'
        upload_bytes(path, uploaded.read(), uploaded.content_type or 'application/octet-stream')
        with transaction.atomic():
            batch = UploadBatch.objects.create(filename=uploaded.name, storage_path=path, uploaded_by=request.user)
            transaction.on_commit(lambda: publish(parse_upload_batch, batch.id))
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

    def retrieve(self, request, pk=None):
        batch = self.get_object()
        payload = self.get_serializer(batch).data
        if request.query_params.get('include_rows') == 'true':
            payload['rows'] = UploadRowSerializer(batch.rows.select_related('duplicate_of').order_by('row_number'), many=True).data
        return Response(payload)

    @action(detail=True, methods=['post'], url_path='resolve-duplicates')
    @transaction.atomic
    def resolve_duplicates(self, request, pk=None):
        batch = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if batch.status != UploadBatch.Status.READY:
            raise ValidationError({'detail': 'This upload is not ready for review.'})
        serializer = ResolveRowsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approved_phones = set()
        for item in serializer.validated_data['rows']:
            row = batch.rows.filter(pk=item['id']).first()
            if not row or row.validation_error or not (row.duplicate_of_id or row.data.get('_duplicate_type')):
                raise ValidationError({'rows': 'Choose a valid duplicate row from this upload.'})
            if item['resolution'] == 'APPROVE':
                if row.normalized_phone in approved_phones:
                    raise ValidationError({'rows': 'Approve only one row for each phone number.'})
                approved_phones.add(row.normalized_phone)
                row.resolution = UploadRow.Resolution.OVERWRITE if row.duplicate_of_id else UploadRow.Resolution.IMPORT
                # One chosen record per phone, including repeated CRM/Intake matches.
                batch.rows.filter(normalized_phone=row.normalized_phone).exclude(pk=row.pk).update(resolution=UploadRow.Resolution.SKIP, resolution_explicit=True)
            else:
                row.resolution = UploadRow.Resolution.SKIP
            row.resolution_explicit = True
            row.save(update_fields=['resolution', 'resolution_explicit'])
        refresh_counts(batch)
        return Response({'detail': 'Duplicate choices saved.', 'duplicates_found': batch.duplicates_found})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def commit(self, request, pk=None):
        batch = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if batch.status == UploadBatch.Status.COMMITTED:
            return Response({'created': 0, 'overwritten': 0, 'skipped': batch.skipped, 'already_committed': True})
        if batch.status != UploadBatch.Status.READY:
            raise ValidationError({'detail': 'This upload is not ready to import.'})
        if batch.mapping_version_id:
            raise ValidationError({'detail': 'This upload used an old mapping template. Upload a file using Download sample format.'})
        rows = list(batch.rows.order_by('row_number'))
        lock_phones(*(row.normalized_phone for row in rows))
        previous = [(row.duplicate_of_id, row.resolution, row.resolution_explicit) for row in rows]
        for row in rows:
            _, errors = validate_customer({**row.data, 'phone': row.normalized_phone}, excel=True)
            if row.answers_expired:
                errors['file'] = 'This upload has expired. Upload the file again.'
            row.validation_errors = errors
            row.validation_error = ' '.join(errors.values())
        classify_rows(batch, rows, preserve_choices=True)
        UploadRow.objects.bulk_update(rows, ['data', 'duplicate_of', 'resolution', 'resolution_explicit', 'validation_errors', 'validation_error'])
        refresh_counts(batch)
        if any(row.validation_error for row in rows):
            return Response({'detail': 'Correct the listed row errors in your spreadsheet and upload it again. No leads were imported.'}, status=400)
        changed = previous != [(row.duplicate_of_id, row.resolution, row.resolution_explicit) for row in rows]
        if any(row.resolution == UploadRow.Resolution.PENDING for row in rows) or changed:
            return Response({'detail': 'Review and approve or reject the duplicate rows before importing. Phone matches are checked again at import; no leads were imported.'}, status=409)
        selected = [row for row in rows if row.resolution != UploadRow.Resolution.SKIP]
        if len({row.normalized_phone for row in selected}) != len(selected):
            raise ValidationError({'detail': 'Choose only one row for each phone number.'})
        created = overwritten = 0
        for row in selected:
            data, _ = validate_customer({**row.data, 'phone': row.normalized_phone}, excel=True)
            duplicate = Lead.objects.filter(phone=row.normalized_phone, deleted_at__isnull=True).order_by('id').first()
            if duplicate:
                if row.resolution != UploadRow.Resolution.OVERWRITE or not row.resolution_explicit or duplicate.pk != row.duplicate_of_id:
                    raise ValidationError({'detail': 'This phone already exists. Review its duplicate match before importing.'})
                lead = Lead.objects.select_for_update().get(pk=duplicate.pk)
                updates = {field: value for field, value in data.items() if field in (*COLUMNS, 'source_label') and value not in ('', None)}
                before = {field: str(getattr(lead, field) or '') for field in updates}
                for field, value in updates.items():
                    setattr(lead, field, value)
                lead.save(update_fields=[*updates, 'updated_at'])
                LeadAudit.objects.create(lead=lead, actor=request.user, event='import_overwrite', before=before, after=updates)
                overwritten += 1
            else:
                lead = Lead.objects.create(**data, assigned_so=None, assigned_ps=None, generated_by=None, status=Lead.Status.FRESH)
                LeadAudit.objects.create(lead=lead, actor=request.user, event='imported')
                created += 1
        batch.status = UploadBatch.Status.COMMITTED
        batch.committed_at = timezone.now()
        batch.skipped = len(rows) - len(selected)
        batch.save(update_fields=['status', 'committed_at', 'skipped'])
        batch.rows.update(answers=[])
        transaction.on_commit(lambda: delete_original(batch.id))
        return Response({'created': created, 'overwritten': overwritten, 'skipped': batch.skipped})
