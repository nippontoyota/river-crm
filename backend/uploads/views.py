from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.permissions import IsAdmin
from intake.mapping import FIELDS, map_entries, validate_customer
from intake.models import IntakeAudit, MappingVersion, Submission
from intake.services import UNRESOLVED, publish
from leads.models import Lead, LeadAudit
from leads.phone_lock import lock_phones
from .models import UploadBatch, UploadRow
from .serializers import ResolveRowsSerializer, UploadBatchSerializer, UploadRowSerializer
from .storage import upload_bytes
from .tasks import parse_upload_batch, refresh_counts, delete_original


def template(value):
    if value in (None, ''):
        return None
    try:
        return MappingVersion.objects.get(pk=value, form__isnull=True)
    except (MappingVersion.DoesNotExist, ValueError, TypeError):
        raise ValidationError({'mapping_version': 'Choose an Excel template version.'})


class UploadBatchViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdmin]
    serializer_class = UploadBatchSerializer
    parser_classes = [MultiPartParser, JSONParser]

    def get_queryset(self):
        return UploadBatch.objects.order_by('-created_at')

    def create(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            raise ValidationError({'detail': 'A file is required.'})
        if uploaded.size > 10 * 1024 * 1024 or Path(uploaded.name).suffix.lower() not in {'.csv', '.xlsx'}:
            raise ValidationError({'detail': 'Upload a CSV or XLSX file below 10 MB.'})
        mapping = template(request.data.get('mapping_version'))
        path = f'imports/{timezone.now():%Y/%m}/{timezone.now().timestamp()}-{uploaded.name}'
        upload_bytes(path, uploaded.read(), uploaded.content_type or 'application/octet-stream')
        with transaction.atomic():
            batch = UploadBatch.objects.create(filename=uploaded.name, storage_path=path, uploaded_by=request.user, mapping_version=mapping)
            transaction.on_commit(lambda: publish(parse_upload_batch, batch.id))
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

    def retrieve(self, request, pk=None):
        batch = self.get_object()
        payload = self.get_serializer(batch).data
        if request.query_params.get('include_rows') == 'true':
            payload['rows'] = UploadRowSerializer(batch.rows.all().order_by('row_number'), many=True).data
        return Response(payload)

    @action(detail=True, methods=['post'], url_path='resolve-duplicates')
    @transaction.atomic
    def resolve_duplicates(self, request, pk=None):
        batch = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if batch.status != UploadBatch.Status.READY:
            raise ValidationError({'detail': 'This upload is not ready for review.'})
        serializer = ResolveRowsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data['rows']:
            batch.rows.filter(pk=item['id']).update(resolution=item['resolution'], resolution_explicit=True)
        refresh_counts(batch)
        return Response({'detail': 'Duplicate choices saved.', 'duplicates_found': batch.duplicates_found})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reparse(self, request, pk=None):
        batch = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if batch.status == UploadBatch.Status.COMMITTED:
            raise ValidationError({'detail': 'Committed batches cannot be reparsed.'})
        if batch.rows.filter(answers_expired=True).exists() or (batch.original_deleted_at and not batch.rows.exists()):
            raise ValidationError({'detail': 'Input expired. Correct rows or upload a new file.'})
        batch.mapping_version = template(request.data.get('mapping_version'))
        batch.status = UploadBatch.Status.PARSING
        batch.save(update_fields=['mapping_version', 'status'])
        IntakeAudit.objects.create(actor=request.user, mapping_version=batch.mapping_version, action='excel_reparse')
        transaction.on_commit(lambda: publish(parse_upload_batch, batch.id))
        return Response(self.get_serializer(batch).data, status=202)

    @action(detail=True, methods=['post'], url_path='correct-row')
    @transaction.atomic
    def correct_row(self, request, pk=None):
        batch = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if batch.status != UploadBatch.Status.READY:
            raise ValidationError({'detail': 'This upload is not ready for review.'})
        row = batch.rows.filter(pk=request.data.get('row_id')).first()
        corrections = request.data.get('corrections')
        if not row or not isinstance(corrections, dict) or set(corrections) - set(FIELDS) - {'source'}:
            raise ValidationError({'detail': 'Choose a row and supply approved customer fields only.'})
        if any(v is not None and not isinstance(v, (str, int, float)) for v in corrections.values()):
            raise ValidationError({'corrections': 'Use scalar customer values.'})
        if row.answers_expired:
            values, errors = validate_customer(corrections, excel=True)
        else:
            values, errors = validate_customer({**row.data, 'phone': row.normalized_phone, **corrections}, excel=True)
            # Preserve unresolved mapping conflicts in fields the admin did not correct.
            errors = {**{k: v for k, v in row.validation_errors.items() if k not in corrections}, **errors}
        row.normalized_phone = values.pop('phone')
        row.data = values
        row.validation_errors = errors
        row.validation_error = ' '.join(errors.values())
        row.answers_expired = False
        row.save()
        refresh_counts(batch)
        IntakeAudit.objects.create(actor=request.user, mapping_version=batch.mapping_version, action='excel_row_corrected')
        return Response(UploadRowSerializer(row).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def commit(self, request, pk=None):
        batch = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if batch.status == UploadBatch.Status.COMMITTED:
            return Response({'created': 0, 'overwritten': 0, 'skipped': batch.skipped, 'already_committed': True})
        if batch.status != UploadBatch.Status.READY:
            raise ValidationError({'detail': 'This upload is not ready to commit.'})
        rows = list(batch.rows.select_related('duplicate_of').order_by('row_number'))
        if any(row.resolution == UploadRow.Resolution.PENDING for row in rows):
            raise ValidationError({'detail': 'Resolve every duplicate before committing.'})
        lock_phones(*(row.normalized_phone for row in rows))
        created = overwritten = skipped = 0
        for row in rows:
            if row.resolution == UploadRow.Resolution.SKIP:
                skipped += 1
                continue
            data, errors = validate_customer({**row.data, 'phone': row.normalized_phone}, excel=True)
            errors = {**row.validation_errors, **errors}
            if row.validation_error or errors or row.answers_expired:
                row.validation_errors = errors
                row.validation_error = ' '.join(errors.values()) or row.validation_error
                row.save(update_fields=['validation_errors', 'validation_error'])
                skipped += 1
                continue
            matches = Lead.objects.filter(phone=data['phone'], deleted_at__isnull=True).order_by('id')
            duplicate = matches.first()
            pending = Submission.objects.filter(normalized_phone=data['phone'], state__in=UNRESOLVED).exists()
            if (duplicate or pending) and not row.resolution_explicit:
                row.resolution = UploadRow.Resolution.SKIP
                row.duplicate_of = duplicate
                row.data['_duplicate_type'] = 'CRM' if duplicate else 'INTAKE'
                row.save(update_fields=['resolution', 'duplicate_of', 'data'])
                skipped += 1
                continue
            if row.resolution == UploadRow.Resolution.OVERWRITE:
                # Only overwrite the explicitly reviewed target, still matching this phone.
                lead = matches.select_for_update().filter(pk=row.duplicate_of_id).first()
                if not lead:
                    raise ValidationError({'detail': 'An overwrite target changed. Review duplicates again.'})
                for field, value in data.items():
                    setattr(lead, field, value)
                lead.save(update_fields=[*data, 'updated_at'])
                event = 'import_overwrite'
                overwritten += 1
            else:
                lead = Lead.objects.create(**data, duplicate_flag=bool(duplicate or pending), assigned_so=None, assigned_ps=None, generated_by=None, status=Lead.Status.FRESH)
                event = 'imported'
                created += 1
            LeadAudit.objects.create(lead=lead, actor=request.user, event=event)
        batch.status = UploadBatch.Status.COMMITTED
        batch.committed_at = timezone.now()
        batch.skipped = skipped
        batch.save(update_fields=['status', 'committed_at', 'skipped'])
        batch.rows.update(answers=[])
        batch.rows.exclude(validation_error="").update(data={}, normalized_phone="")
        transaction.on_commit(lambda: delete_original(batch.id))
        return Response({'created': created, 'overwritten': overwritten, 'skipped': skipped})
