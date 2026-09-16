import csv
import io
from datetime import date, datetime

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from intake.mapping import map_entries, normalize_phone, parse_date, sanitize_entries
from intake.models import Submission
from intake.services import UNRESOLVED
from leads.models import Lead
from leads.serializers import configured_source
from .models import UploadBatch, UploadRow
from .storage import delete_paths, download_bytes


def classify_source(raw):
    source = configured_source(raw)
    return source or raw.strip(), raw, '' if source else 'Choose a lead source from Admin Lists.'


def read_rows(filename, content):
    if filename.lower().endswith('.csv'):
        rows = csv.reader(io.StringIO(content.decode('utf-8-sig')))
        headers = next(rows, [])
        for values in rows:
            yield [{'id': f'column:{index + 1}', 'label': str(headers[index] or '') if index < len(headers) else f'Column {index + 1}', 'value': value}
                   for index, value in enumerate(values + [''] * max(0, len(headers) - len(values)))]
        return
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = next(rows, [])
        for values in rows:
            yield [{'id': f'column:{index + 1}', 'label': str(headers[index] or '') if index < len(headers) else f'Column {index + 1}',
                    'value': value.date().isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else value}
                   for index, value in enumerate(values)]
    finally:
        workbook.close()


def classify_rows(batch, rows, preserve_choices=False):
    phones = {row.normalized_phone for row in rows if row.normalized_phone}
    existing = {}
    for lead in Lead.objects.filter(phone__in=phones, deleted_at__isnull=True).only('id', 'phone').order_by('id'):
        existing.setdefault(lead.phone, lead)
    pending = set(Submission.objects.filter(normalized_phone__in=phones, state__in=UNRESOLVED).values_list('normalized_phone', flat=True))
    first = {}
    for row in rows:
        previous_match = (row.duplicate_of_id, row.data.get('_duplicate_type'), row.data.get('_duplicate_label'))
        previous_resolution = row.resolution
        for key in list(row.data):
            if key.startswith('_'):
                del row.data[key]
        row.duplicate_of = None
        row.resolution = UploadRow.Resolution.IMPORT
        row.duplicate_of = existing.get(row.normalized_phone) if not row.validation_error else None
        if row.validation_error:
            pass
        elif row.duplicate_of:
            row.data['_duplicate_type'] = 'CRM'
            row.resolution = UploadRow.Resolution.SKIP
        elif row.normalized_phone in pending:
            row.data['_duplicate_type'] = 'INTAKE'
            row.data['_duplicate_label'] = 'Pending Lead Intake enquiry'
            row.resolution = UploadRow.Resolution.SKIP
        elif row.normalized_phone in first:
            row.data['_duplicate_type'] = 'FILE'
            row.data['_duplicate_label'] = f'Row {first[row.normalized_phone]}'
            row.resolution = UploadRow.Resolution.SKIP
        else:
            first[row.normalized_phone] = row.row_number
        current_match = (row.duplicate_of_id, row.data.get('_duplicate_type'), row.data.get('_duplicate_label'))
        if preserve_choices and row.resolution_explicit and previous_match == current_match:
            row.resolution = previous_resolution
        else:
            row.resolution_explicit = False
    return rows


def refresh_counts(batch):
    rows = list(batch.rows.all())
    batch.total_rows = len(rows)
    batch.parsed_ok = sum(not r.validation_error and r.resolution != UploadRow.Resolution.SKIP for r in rows)
    batch.duplicates_found = sum(r.resolution == UploadRow.Resolution.PENDING for r in rows)
    batch.skipped = sum(bool(r.validation_error) or r.resolution == UploadRow.Resolution.SKIP for r in rows)
    batch.save(update_fields=['total_rows', 'parsed_ok', 'duplicates_found', 'skipped'])


def delete_original(batch_id):
    batch = UploadBatch.objects.get(pk=batch_id)
    if batch.original_deleted_at:
        return
    try:
        delete_paths([batch.storage_path])
    except Exception:
        return  # Retention retries this deletion without logging the path or credentials.
    UploadBatch.objects.filter(pk=batch_id).update(original_deleted_at=timezone.now())


@shared_task(ignore_result=True)
def parse_upload_batch(batch_id):
    try:
        with transaction.atomic():
            batch = UploadBatch.objects.select_for_update(of=('self',)).select_related('mapping_version').get(pk=batch_id)
            if batch.status == UploadBatch.Status.COMMITTED:
                return
            if batch.status != UploadBatch.Status.PARSING:
                return
            rules = batch.mapping_version.rules if batch.mapping_version else {}
            previous = list(batch.rows.all().order_by('row_number'))
            if previous:
                incoming = [(row.row_number, row.answers) for row in previous]
            elif not batch.original_deleted_at:
                incoming = enumerate(read_rows(batch.filename, download_bytes(batch.storage_path)), start=2)
            else:
                raise ValueError('Original input expired.')
            rows = []
            for row_number, entries in incoming:
                if not previous and all(entry['value'] is None or str(entry['value']).strip() == '' for entry in entries):
                    continue
                retained, ignored = sanitize_entries(entries, rules, excel=True)
                result = map_entries(retained, rules, excel=True)
                data = result['values']
                phone = normalize_phone(data.pop('phone'))
                if not data.get('source_label'):
                    data['source_label'] = next((str(e['value'] or '').strip() for e in retained if e['label'].strip().casefold() == 'source'), '')
                    if len(data['source_label']) > 100:
                        result['errors']['source_label'] = 'Maximum length is 100 characters.'
                rows.append(UploadRow(batch=batch, row_number=row_number, answers=retained, ignored_labels=ignored,
                    data=data, normalized_phone=phone, validation_error=' '.join(result['errors'].values()), validation_errors=result['errors']))
            classify_rows(batch, rows)
            batch.rows.all().delete()
            UploadRow.objects.bulk_create(rows)
            batch.status = UploadBatch.Status.READY
            batch.error_message = ''
            batch.save(update_fields=['status', 'error_message'])
            refresh_counts(batch)
            # Once parsed, sanitized entries are sufficient for mapping/reparse.
            # Delete the original immediately so ignored/prohibited answers cannot linger in a file.
            transaction.on_commit(lambda: delete_original(batch.id))
    except Exception:
        UploadBatch.objects.filter(pk=batch_id).exclude(status=UploadBatch.Status.COMMITTED).update(status=UploadBatch.Status.FAILED, error_message='Unable to parse this file. Check the file format and retry.')
