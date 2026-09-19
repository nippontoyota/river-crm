import csv
import hashlib
import io
from collections import Counter, defaultdict
from zipfile import ZipFile

from celery import shared_task
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from intake.mapping import normalize_phone, string, validate_customer
from intake.models import Submission
from intake.services import UNRESOLVED
from leads.models import Lead
from .models import UploadBatch, UploadRow
from .storage import delete_paths, download_bytes


# These headings match Download sample format. No aliases or saved mappings.
HEADINGS = ('name', 'phone', 'email', 'source', 'enquiry date', 'city', 'pincode')
COLUMNS = ('name', 'phone', 'email', 'source', 'enquiry_date', 'city', 'pincode')
MAX_ROWS = 1000
MAX_EXPANDED_BYTES = 25 * 1024 * 1024
WRITE_CHUNK = 100
GROUP_SAMPLE_SIZE = 20
ROW_LIMIT_MESSAGE = 'Upload at most 1,000 leads per file. Split this spreadsheet into smaller files and upload them separately.'
DUPLICATE_ROWS = Q(duplicate_of__isnull=False) | Q(data___duplicate_type__in=['CRM', 'FILE', 'INTAKE'])


class FileFormatError(ValueError):
    pass


def validate_headings(headers):
    labels = [string(value) for value in headers]
    missing = [label for label in HEADINGS if label not in labels]
    unexpected = [label for label in labels if label and label not in HEADINGS]
    repeated = [label for label, count in Counter(labels).items() if label and count > 1]
    blank = [str(index + 1) for index, label in enumerate(labels) if not label]
    errors = []
    if missing:
        errors.append(f'Missing headings: {", ".join(missing)}.')
    if unexpected:
        errors.append(f'Unrecognized headings: {", ".join(unexpected)}.')
    if repeated:
        errors.append(f'Repeated headings: {", ".join(repeated)}.')
    if blank:
        errors.append(f'Blank headings in columns: {", ".join(blank)}.')
    if errors:
        raise FileFormatError('Invalid file headings. ' + ' '.join(errors) + ' Use the headings in Download sample format, then upload the corrected file.')
    return labels


def read_rows(filename, content):
    workbook = None
    try:
        if filename.lower().endswith('.csv'):
            rows = csv.reader(io.StringIO(content.decode('utf-8-sig')), strict=True)
        else:
            with ZipFile(io.BytesIO(content)) as archive:
                if sum(entry.file_size for entry in archive.infolist()) > MAX_EXPANDED_BYTES:
                    raise FileFormatError('This XLSX file expands beyond 25 MB. Remove unused sheets/formatting or save a smaller CSV and upload it again.')
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            rows = workbook.active.iter_rows(values_only=True)
        headings = validate_headings(next(rows, []))
        columns = [COLUMNS[HEADINGS.index(label)] for label in headings]
        count = 0
        for number, values in enumerate(rows, start=2):
            if all(not string(value) for value in values):
                continue
            count += 1
            if count > MAX_ROWS:
                raise FileFormatError(ROW_LIMIT_MESSAGE)
            if len(values) != len(headings):
                raise FileFormatError(f'Row {number} has {len(values)} cells; expected {len(headings)}. Keep the same columns as the sample and upload the corrected file.')
            yield number, dict(zip(columns, values))
    finally:
        if workbook:
            workbook.close()


def group_fingerprint(numbers):
    return hashlib.sha256(','.join(map(str, sorted(numbers))).encode()).hexdigest()


def match_identity(row):
    # Legacy batches stored the complete group; keep their approvals valid.
    numbers = row.data.get('_file_rows', [])
    fingerprint = row.data.get('_file_group') or (group_fingerprint(numbers) if numbers else '')
    return row.duplicate_of_id, row.data.get('_duplicate_type'), fingerprint


def classify_rows(batch, rows, preserve_choices=False):
    groups = defaultdict(list)
    for row in rows:
        if row.normalized_phone and not row.validation_error:
            groups[row.normalized_phone].append(row.row_number)
    existing = {}
    for lead in Lead.objects.filter(phone__in=groups, deleted_at__isnull=True).only('id', 'phone').order_by('id').iterator(chunk_size=WRITE_CHUNK):
        existing.setdefault(lead.phone, lead)
    pending = set(Submission.objects.filter(normalized_phone__in=groups, state__in=UNRESOLVED).values_list('normalized_phone', flat=True))
    group_details = {phone: {'_file_rows': sorted(numbers)[:GROUP_SAMPLE_SIZE], '_file_row_count': len(numbers), '_file_group': group_fingerprint(numbers)}
                     for phone, numbers in groups.items() if len(numbers) > 1}
    for row in rows:
        previous_match = match_identity(row)
        previous_resolution = row.resolution
        row.data = {key: value for key, value in row.data.items() if not key.startswith('_')}
        row.duplicate_of = existing.get(row.normalized_phone) if not row.validation_error else None
        row.resolution = UploadRow.Resolution.IMPORT
        if not row.validation_error:
            file_rows = groups[row.normalized_phone]
            if len(file_rows) > 1:
                row.data.update(group_details[row.normalized_phone])
            if row.duplicate_of:
                row.data['_duplicate_type'] = 'CRM'
            elif row.normalized_phone in pending:
                row.data['_duplicate_type'] = 'INTAKE'
                row.data['_duplicate_label'] = 'Pending Lead Intake enquiry'
            elif len(file_rows) > 1:
                row.data['_duplicate_type'] = 'FILE'
                row.data['_duplicate_label'] = 'Repeated in this file'
            if row.data.get('_duplicate_type'):
                row.resolution = UploadRow.Resolution.PENDING
        current_match = match_identity(row)
        if preserve_choices and row.resolution_explicit and previous_match == current_match:
            row.resolution = previous_resolution
        else:
            row.resolution_explicit = False
    return rows


def refresh_counts(batch):
    counts = batch.rows.aggregate(
        total_rows=Count('pk'),
        parsed_ok=Count('pk', filter=Q(validation_error='', resolution__in=['IMPORT', 'OVERWRITE'])),
        duplicates_found=Count('pk', filter=Q(resolution='PENDING')),
        skipped=Count('pk', filter=Q(resolution='SKIP')),
    )
    for field, value in counts.items():
        setattr(batch, field, value)
    batch.save(update_fields=['total_rows', 'parsed_ok', 'duplicates_found', 'skipped'])


def delete_original(batch_id):
    batch = UploadBatch.objects.get(pk=batch_id)
    if batch.original_deleted_at:
        return
    try:
        delete_paths([batch.storage_path])
    except Exception:
        return  # Retention retries deletion without logging paths or credentials.
    UploadBatch.objects.filter(pk=batch_id).update(original_deleted_at=timezone.now())


@shared_task(ignore_result=True)
def parse_upload_batch(batch_id):
    try:
        with transaction.atomic():
            batch = UploadBatch.objects.select_for_update().get(pk=batch_id)
            if batch.status != UploadBatch.Status.PARSING:
                return
            if batch.original_deleted_at:
                raise FileFormatError('Original file expired. Upload the corrected file again.')
            rows = []
            for row_number, values in read_rows(batch.filename, download_bytes(batch.storage_path)):
                values['source_label'] = string(values.get('source'))
                data, errors = validate_customer(values, excel=True)
                phone = normalize_phone(data.pop('phone'))
                rows.append(UploadRow(batch=batch, row_number=row_number, data=data, normalized_phone=phone,
                    validation_error=' '.join(errors.values()), validation_errors=errors))
            if not rows:
                raise FileFormatError('The file has headings but no leads. Add lead rows below the headings and upload it again.')
            classify_rows(batch, rows)
            batch.rows.all().delete()
            for offset in range(0, len(rows), WRITE_CHUNK):
                UploadRow.objects.bulk_create(rows[offset:offset + WRITE_CHUNK])
            batch.status = UploadBatch.Status.READY
            batch.error_message = ''
            batch.save(update_fields=['status', 'error_message'])
            refresh_counts(batch)
            transaction.on_commit(lambda: delete_original(batch.id))
    except Exception as error:
        message = str(error) if isinstance(error, FileFormatError) else 'Unable to read this file. Save it as CSV (UTF-8) or XLSX using Download sample format and upload it again.'
        UploadBatch.objects.filter(pk=batch_id).exclude(status=UploadBatch.Status.COMMITTED).update(status=UploadBatch.Status.FAILED, error_message=message)
        delete_original(batch_id)
