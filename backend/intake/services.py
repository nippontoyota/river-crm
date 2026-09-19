import hashlib
import hmac
import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from leads.models import Lead, LeadAudit
from leads.phone_lock import lock_phones
from .mapping import FIELDS, map_entries, normalize_phone, sanitize_entries, validate_customer
from .models import Connection, IntakeAudit, Submission

TERMINAL = (Submission.State.IMPORTED, Submission.State.LINKED, Submission.State.DISMISSED)
UNRESOLVED = (Submission.State.RECEIVED, Submission.State.PROCESSING, Submission.State.NEEDS_REVIEW, Submission.State.FAILED)


def secret_config(connection):
    return settings.INTAKE_SECRETS.get(connection.secret_ref, {})


def payload_fingerprint(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hmac.new(settings.INTAKE_FINGERPRINT_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def publish(task, *args):
    # A committed receipt is the queue. Publication errors must not reject it or log answers.
    if settings.INTAKE_EXECUTION_MODE == 'database':
        return False  # The scheduled processor reads pending work from the database.
    try:
        task.apply_async(args=args, retry=False)
    except Exception:
        return False
    return True


def enqueue(receipt_id):
    from .tasks import process_submission
    transaction.on_commit(lambda: publish(process_submission, str(receipt_id)))


def record(submission, action, actor=None):
    IntakeAudit.objects.create(submission=submission, connection=submission.connection, mapping_version=submission.mapping_version, lead=submission.lead, actor=actor, action=action)
    if submission.lead_id:
        LeadAudit.objects.create(lead=submission.lead, actor=actor, event='intake_' + action, after={'receipt_id': str(submission.pk)})


def touch_connection(connection_id, field, when):
    try:
        Connection.objects.filter(pk=connection_id).update(**{field: when})
    except Exception:
        pass  # Receipt timestamps remain the authoritative health data.


def latest_mapping(form):
    return form.mappings.order_by('-version').first()


def accept(form, external_id, fingerprint='', entries=None, submitted_at=None, attribution=None):
    """Unique identity handles concurrent deliveries; phone locks serialize CRM writes."""
    connection = form.connection
    identity = external_id if connection.origin == Connection.Origin.META else f'{form.external_id}:{external_id}'
    existing = Submission.objects.filter(connection=connection, identity=identity).first()
    if existing:
        if fingerprint and not hmac.compare_digest(existing.fingerprint, fingerprint):
            return existing, True
        return existing, False
    mapping = latest_mapping(form)
    rules = mapping.rules if mapping else {}
    answers, ignored = sanitize_entries(entries or [], rules)
    mapped = map_entries(answers, rules) if entries is not None else {'values': {}, 'errors': {}}
    now = timezone.now()
    lock_phones(normalize_phone(mapped['values'].get('phone')))
    receipt, created = Submission.objects.get_or_create(connection=connection, identity=identity, defaults={
        'form': form, 'external_id': external_id, 'fingerprint': fingerprint, 'source': connection.source,
        'submitted_at': submitted_at, 'answers': answers, 'ignored_labels': ignored, 'mapped_values': mapped['values'],
        'normalized_phone': normalize_phone(mapped['values'].get('phone')), 'mapping_version': mapping,
        'attribution': attribution or {}, 'fetched_at': now if entries is not None else None,
    })
    if not created:
        return receipt, bool(fingerprint and not hmac.compare_digest(receipt.fingerprint, fingerprint))
    transaction.on_commit(lambda: touch_connection(connection.pk, 'last_receipt_at', now))
    record(receipt, 'received')
    enqueue(receipt.pk)
    return receipt, False


def matching_leads(phone):
    return Lead.objects.filter(phone=phone, deleted_at__isnull=True).order_by('id') if phone else Lead.objects.none()


def earlier_pending(receipt):
    return Submission.objects.filter(normalized_phone=receipt.normalized_phone, state__in=UNRESOLVED).filter(
        Q(received_at__lt=receipt.received_at) | Q(received_at=receipt.received_at, id__lt=receipt.pk)
    ).exclude(pk=receipt.pk).order_by('received_at', 'id').first()


def finish(receipt, state):
    receipt.state = state
    receipt.resolved_at = timezone.now()
    receipt.answers = []
    receipt.corrections = {}
    receipt.errors = {}
    receipt.review_reason = ''
    receipt.next_attempt_at = None
    receipt.lease_until = None
    receipt.lease_token = None
    receipt.blocked_by = None
    # Unknown answers are gone. Validated fields and allowlisted attribution remain with the receipt.
    if state == Submission.State.LINKED:
        validated, errors = validate_customer(receipt.mapped_values)
        receipt.mapped_values = {key: value for key, value in validated.items() if key not in errors}
    if state == Submission.State.DISMISSED:
        receipt.mapped_values = {}
        receipt.normalized_phone = ''
    receipt.save()
    transaction.on_commit(lambda: release_blocked(receipt.pk))


def release_blocked(receipt_id):
    try:
        Submission.objects.filter(blocked_by_id=receipt_id, state=Submission.State.NEEDS_REVIEW, answers_expired=False).update(
            state=Submission.State.RECEIVED, next_attempt_at=timezone.now(), blocked_by=None,
        )
    except Exception:
        pass  # The scheduled sweep also checks resolved blockers.


def create_lead(receipt, data, separate=False, actor=None):
    lead = Lead.objects.create(**data, source=receipt.source, status=Lead.Status.FRESH,
        assigned_so=None, assigned_ps=None, generated_by=None, duplicate_flag=separate,
        flagged_to_manager=False, needs_cre_reassignment=False, needs_so_reassignment=False)
    receipt.lead = lead
    receipt.mapped_values = data
    finish(receipt, Submission.State.IMPORTED)
    transaction.on_commit(lambda: touch_connection(receipt.connection_id, 'last_import_at', timezone.now()))
    record(receipt, 'created_separately' if separate else 'imported', actor)
    return lead


def process_locked(receipt, separate=False, actor=None):
    if receipt.answers_expired:
        receipt.state = Submission.State.NEEDS_REVIEW
        receipt.review_reason = 'expired'
        receipt.errors = {'input': 'Answers expired. Supply corrected customer input before retry.'}
        receipt.next_attempt_at = None
        receipt.save()
        return
    result = map_entries(receipt.answers, receipt.mapping_version.rules if receipt.mapping_version else {}, corrections=receipt.corrections)
    receipt.mapped_values = result['values']
    receipt.normalized_phone = normalize_phone(result['values'].get('phone'))
    receipt.errors = result['errors']
    receipt.lease_until = None
    receipt.lease_token = None
    receipt.next_attempt_at = None
    receipt.blocked_by = None
    if result['errors']:
        receipt.state = Submission.State.NEEDS_REVIEW
        receipt.review_reason = 'validation'
    elif not settings.INTAKE_ENABLED or not receipt.connection.enabled or not receipt.form.enabled or receipt.connection.paused_reason:
        if separate:
            raise ValidationError({'detail': 'Enable this connection and form before creating a separate lead.'})
        receipt.state = Submission.State.RECEIVED
        receipt.review_reason = 'connection'
        receipt.next_attempt_at = timezone.now()
    else:
        lock_phones(receipt.normalized_phone)
        duplicate = matching_leads(receipt.normalized_phone).exists()
        pending = earlier_pending(receipt)
        if not separate and (duplicate or pending):
            receipt.state = Submission.State.NEEDS_REVIEW
            receipt.review_reason = 'existing_lead' if duplicate else 'pending_submission'
            receipt.errors = {'duplicate': 'Review the matching lead.' if duplicate else 'Waiting for an earlier matching enquiry.'}
            if not duplicate:
                receipt.blocked_by = pending
                receipt.next_attempt_at = timezone.now() + timedelta(minutes=1)
        else:
            create_lead(receipt, result['values'], separate, actor)
            return
    receipt.save()


@transaction.atomic
def resolve(receipt_id, action, actor, corrections=None, lead_id=None):
    receipt = Submission.objects.select_for_update(no_key=True).get(pk=receipt_id)
    if receipt.state in TERMINAL:
        return receipt  # Simultaneous or repeated review actions cannot make another lead.
    if receipt.state == Submission.State.PROCESSING and receipt.lease_until and receipt.lease_until > timezone.now():
        raise ValidationError({'detail': 'This receipt is processing. Try again after it finishes.'})
    if action == 'dismiss':
        finish(receipt, Submission.State.DISMISSED)
        record(receipt, 'dismissed', actor)
        return receipt
    if action == 'link':
        lead = Lead.objects.filter(pk=lead_id, deleted_at__isnull=True).first()
        if not lead:
            raise ValidationError({'lead_id': 'Choose a current lead.'})
        lock_phones(lead.phone, receipt.normalized_phone)
        lead = Lead.objects.select_for_update().get(pk=lead.pk)
        if lead.deleted_at:
            raise ValidationError({'lead_id': 'Choose a current lead.'})
        receipt.lead = lead
        finish(receipt, Submission.State.LINKED)
        record(receipt, 'linked', actor)
        return receipt
    if action == 'correct':
        if not isinstance(corrections, dict) or not corrections or set(corrections) - set(FIELDS):
            raise ValidationError({'corrections': 'Supply approved customer fields only.'})
        if any(v is not None and not isinstance(v, (str, int, float)) for v in corrections.values()):
            raise ValidationError({'corrections': 'Use scalar customer values.'})
        if receipt.answers_expired:
            _, errors = validate_customer(corrections)
            if errors:
                raise ValidationError(errors)
            receipt.answers_expired = False
            receipt.answers = []
            receipt.fetched_at = timezone.now()  # Corrected expired Meta records must never refetch.
        receipt.corrections.update(corrections)
        record(receipt, 'corrected', actor)
        if receipt.connection.origin == 'META' and not receipt.fetched_at:
            receipt.state = Submission.State.RECEIVED
            receipt.next_attempt_at = timezone.now()
            receipt.save()
            enqueue(receipt.pk)
        else:
            process_locked(receipt, actor=actor)
    elif action == 'create_separately':
        process_locked(receipt, separate=True, actor=actor)
    elif action == 'retry':
        if receipt.answers_expired:
            raise ValidationError({'detail': 'Answers expired. Supply corrected input first.'})
        receipt.state = Submission.State.RECEIVED
        receipt.attempts = 0
        receipt.next_attempt_at = timezone.now()
        receipt.lease_until = None
        receipt.lease_token = None
        receipt.save()
        record(receipt, 'retry', actor)
        enqueue(receipt.pk)
    else:
        raise ValidationError({'action': 'Choose a supported resolution.'})
    return receipt
