import csv
import io
from collections import Counter, defaultdict

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from intake.mapping import normalize_phone, string, validate_customer
from intake.models import Submission
from intake.services import UNRESOLVED
from leads.models import Lead
from .models import UploadBatch, UploadRow
from .storage import delete_paths, download_bytes


# These headings match Download sample format. No aliases or saved mappings.
HEADINGS = ('name', 'phone', 'email', 'source', 'enquiry date')
COLUMNS = ('name', 'phone', 'email', 'source', 'enquiry_date')


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
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            rows = workbook.active.iter_rows(values_only=True)
        headings = validate_headings(next(rows, []))
        columns = [COLUMNS[HEADINGS.index(label)] for label in headings]
        for number, values in enumerate(rows, start=2):
            if all(not string(value) for value in values):
                continue
            if len(values) != len(headings):
                raise FileFormatError(f'Row {number} has {len(values)} cells; expected {len(headings)}. Keep the same columns as the sample and upload the corrected file.')
            yield number, dict(zip(columns, values))
    finally:
        if workbook:
            workbook.close()


def classify_rows(batch, rows, preserve_choices=False):
    groups = defaultdict(list)
    for row in rows:
        if row.normalized_phone and not row.validation_error:
            groups[row.normalized_phone].append(row.row_number)
    existing = {}
    for lead in Lead.objects.filter(phone__in=groups, deleted_at__isnull=True).only('id', 'phone').order_by('id'):
        existing.setdefault(lead.phone, lead)
    pending = set(Submission.objects.filter(normalized_phone__in=groups, state__in=UNRESOLVED).values_list('normalized_phone', flat=True))
    for row in rows:
        previous_match = (row.duplicate_of_id, row.data.get('_duplicate_type'), row.data.get('_file_rows'))
        previous_resolution = row.resolution
        row.data = {key: value for key, value in row.data.items() if not key.startswith('_')}
        row.duplicate_of = existing.get(row.normalized_phone) if not row.validation_error else None
        row.resolution = UploadRow.Resolution.IMPORT
        if not row.validation_error:
            file_rows = groups[row.normalized_phone]
            if len(file_rows) > 1:
                row.data['_file_rows'] = file_rows
            if row.duplicate_of:
                row.data['_duplicate_type'] = 'CRM'
            elif row.normalized_phone in pending:
                row.data['_duplicate_type'] = 'INTAKE'
                row.data['_duplicate_label'] = 'Pending Lead Intake enquiry'
            elif len(file_rows) > 1:
                row.data['_duplicate_type'] = 'FILE'
                row.data['_duplicate_label'] = 'Rows ' + ', '.join(map(str, file_rows))
            if row.data.get('_duplicate_type'):
                row.resolution = UploadRow.Resolution.PENDING
        current_match = (row.duplicate_of_id, row.data.get('_duplicate_type'), row.data.get('_file_rows'))
        if preserve_choices and row.resolution_explicit and previous_match == current_match:
            row.resolution = previous_resolution
        else:
            row.resolution_explicit = False
    return rows


def refresh_counts(batch):
    rows = list(batch.rows.all())
    batch.total_rows = len(rows)
    batch.parsed_ok = sum(not r.validation_error and r.resolution in {UploadRow.Resolution.IMPORT, UploadRow.Resolution.OVERWRITE} for r in rows)
    batch.duplicates_found = sum(r.resolution == UploadRow.Resolution.PENDING for r in rows)
    batch.skipped = sum(r.resolution == UploadRow.Resolution.SKIP for r in rows)
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
            UploadRow.objects.bulk_create(rows)
            batch.status = UploadBatch.Status.READY
            batch.error_message = ''
            batch.save(update_fields=['status', 'error_message'])
            refresh_counts(batch)
            transaction.on_commit(lambda: delete_original(batch.id))
    except Exception as error:
        message = str(error) if isinstance(error, FileFormatError) else 'Unable to read this file. Save it as CSV (UTF-8) or XLSX using Download sample format and upload it again.'
        UploadBatch.objects.filter(pk=batch_id).exclude(status=UploadBatch.Status.COMMITTED).update(status=UploadBatch.Status.FAILED, error_message=message)
        delete_original(batch_id)
