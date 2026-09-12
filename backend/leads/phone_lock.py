"""Every CRM phone write shares the intake transaction's advisory lock."""
import hashlib

from django.db import connection


def lock_phones(*phones):
    if not connection.in_atomic_block:
        raise RuntimeError('Phone locks require a transaction.')
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            for phone in sorted(set(filter(None, phones))):
                key = int.from_bytes(hashlib.sha256(('crm-phone:' + phone).encode()).digest()[:8], 'big', signed=True)
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [key])
    # SQLite serializes writes for local development. Concurrency is tested on PostgreSQL.


def guard_manual_phone(phone, current_id=None):
    from rest_framework.exceptions import ValidationError
    from intake.models import Submission
    from intake.services import UNRESOLVED
    lock_phones(phone)
    # Manual duplicates already supported by the CRM remain supported. Intake
    # enquiries must go through their explicit review decision, including races.
    pending = Submission.objects.filter(normalized_phone=phone, state__in=UNRESOLVED).exists()
    imported = Submission.objects.filter(lead__phone=phone, lead__deleted_at__isnull=True, state__in=['IMPORTED', 'LINKED']).exclude(lead_id=current_id).exists()
    if pending or imported:
        raise ValidationError({'phone': 'This phone has an intake enquiry. Ask an administrator to review it in Lead Intake.'})
