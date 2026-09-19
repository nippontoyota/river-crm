import random
import uuid
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .mapping import map_entries, normalize_phone, sanitize_entries
from .meta import MetaFailure, fetch_lead, form_leads, graph
from .models import Connection, IntakeForm, Submission
from .services import TERMINAL, accept, enqueue, finish, process_locked, publish, record


@shared_task(ignore_result=True)
def process_submission(receipt_id):
    if not settings.INTAKE_ENABLED:
        return
    now = timezone.now()
    token = uuid.uuid4()
    with transaction.atomic():
        receipt = Submission.objects.select_for_update(of=('self',), no_key=True).select_related('connection', 'form', 'mapping_version').get(pk=receipt_id)
        if receipt.state in TERMINAL or receipt.state == Submission.State.FAILED or receipt.answers_expired:
            return
        if not receipt.connection.enabled or not receipt.form.enabled or receipt.connection.paused_reason:
            return
        if receipt.state == Submission.State.NEEDS_REVIEW:
            if receipt.review_reason != 'pending_submission':
                return
            if receipt.blocked_by_id and Submission.objects.filter(pk=receipt.blocked_by_id).exclude(state__in=TERMINAL).exists():
                return
        if receipt.lease_until and receipt.lease_until > now:
            return
        if receipt.next_attempt_at and receipt.next_attempt_at > now:
            return
        if receipt.attempts >= 10:
            receipt.state = Submission.State.FAILED
            receipt.review_reason = 'retry_exhausted'
            receipt.errors = {'processing': 'Retry limit reached. An administrator can retry.'}
            receipt.next_attempt_at = None
            receipt.save()
            return
        receipt.state = Submission.State.PROCESSING
        receipt.attempts += 1
        receipt.lease_until = now + timedelta(minutes=5)
        receipt.lease_token = token
        receipt.save()
    try:
        fetched = None
        fetch_needed = receipt.connection.origin == Connection.Origin.META and not receipt.fetched_at
        if fetch_needed:
            fetched = fetch_lead(receipt)
        with transaction.atomic():
            receipt = Submission.objects.select_for_update(of=('self',), no_key=True).select_related('connection', 'form', 'mapping_version').get(pk=receipt_id)
            if receipt.lease_token != token or receipt.state != Submission.State.PROCESSING:
                return
            if not receipt.connection.enabled or not receipt.form.enabled or receipt.connection.paused_reason:
                receipt.state = Submission.State.RECEIVED
                receipt.lease_until = None
                receipt.lease_token = None
                receipt.save()
                return
            if fetch_needed:
                if fetched is None:
                    finish(receipt, Submission.State.DISMISSED)
                    record(receipt, 'before_activation')
                    return
                entries, receipt.submitted_at, receipt.attribution = fetched
                receipt.answers, receipt.ignored_labels = sanitize_entries(entries, receipt.mapping_version.rules if receipt.mapping_version else {})
                receipt.fetched_at = timezone.now()
            process_locked(receipt)
            if receipt.state == Submission.State.IMPORTED and receipt.attribution.get('campaign_id'):
                if settings.INTAKE_EXECUTION_MODE == 'database':
                    transaction.on_commit(lambda: enrich_campaign.run(str(receipt.pk)))
                else:
                    transaction.on_commit(lambda: publish(enrich_campaign, str(receipt.pk)))
    except Exception as error:
        code = error.code if isinstance(error, MetaFailure) else 'processing_temporarily_unavailable'
        with transaction.atomic():
            receipt = Submission.objects.select_for_update(no_key=True).get(pk=receipt_id)
            if receipt.lease_token != token:
                return
            pause = isinstance(error, MetaFailure) and error.pause
            failed = receipt.attempts >= 10 or (isinstance(error, MetaFailure) and error.permanent)
            receipt.state = Submission.State.FAILED if failed else Submission.State.RECEIVED
            receipt.errors = {'processing': code}
            receipt.review_reason = 'connection' if pause else 'processing'
            receipt.lease_until = None
            receipt.lease_token = None
            receipt.next_attempt_at = None if failed else timezone.now() + timedelta(seconds=min(3600, 15 * 2 ** min(receipt.attempts, 8) + random.uniform(0, 15)))
            receipt.save()
            if pause:
                Connection.objects.filter(pk=receipt.connection_id).update(paused_reason=code)


@shared_task(ignore_result=True)
def sweep_receipts():
    if settings.INTAKE_EXECUTION_MODE == 'database':
        return
    if settings.INTAKE_ENABLED:
        for receipt_id in due_receipts().values_list('pk', flat=True)[:1000]:
            publish(process_submission, str(receipt_id))
    from uploads.models import UploadBatch
    from uploads.tasks import parse_upload_batch
    for batch_id in UploadBatch.objects.filter(status=UploadBatch.Status.PARSING, original_deleted_at__isnull=True).values_list('pk', flat=True)[:100]:
        publish(parse_upload_batch, batch_id)


def due_receipts():
    now = timezone.now()
    return Submission.objects.filter(connection__enabled=True, connection__paused_reason='', form__enabled=True, answers_expired=False).filter(
            Q(state=Submission.State.RECEIVED, next_attempt_at__lte=now) |
            Q(state=Submission.State.PROCESSING, lease_until__lte=now) |
            Q(state=Submission.State.NEEDS_REVIEW, review_reason='pending_submission', next_attempt_at__lte=now)
        ).filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now)).filter(
            Q(blocked_by__isnull=True) | Q(blocked_by__state__in=TERMINAL)
        ).order_by('received_at', 'id')


@shared_task(ignore_result=True)
def reconcile_forms():
    if not settings.INTAKE_ENABLED or settings.INTAKE_EXECUTION_MODE == 'database':
        return
    for form_id in IntakeForm.objects.filter(enabled=True, connection__enabled=True, connection__paused_reason='', connection__origin='META').values_list('pk', flat=True):
        publish(reconcile_form, form_id)


@shared_task(ignore_result=True, soft_time_limit=240)
def reconcile_form(form_id):
    if not settings.INTAKE_ENABLED or settings.INTAKE_EXECUTION_MODE == 'database':
        return
    with transaction.atomic():
        form = IntakeForm.objects.select_for_update().select_related('connection').get(pk=form_id)
        end = timezone.now()
        if not form.enabled or not form.connection.enabled or form.connection.paused_reason or (form.reconcile_lease_until and form.reconcile_lease_until > end):
            return
        lease = end + timedelta(minutes=5)
        form.reconcile_lease_until = lease
        form.save(update_fields=['reconcile_lease_until'])
        start = max(form.activated_at, form.connection.activated_at, (form.checkpoint or form.activated_at) - timedelta(minutes=30))
    try:
        for external_id, submitted in form_leads(form, start, end):
            with transaction.atomic():
                connection = Connection.objects.get(pk=form.connection_id)
                current_form = IntakeForm.objects.get(pk=form.pk)
                if not connection.enabled or connection.paused_reason or not current_form.enabled or current_form.reconcile_lease_until != lease:
                    return
                current_form.connection = connection
                if submitted >= max(current_form.activated_at, connection.activated_at):
                    accept(current_form, external_id, submitted_at=submitted)
        IntakeForm.objects.filter(pk=form.pk, reconcile_lease_until=lease).update(checkpoint=end, last_reconciled_at=timezone.now(), reconcile_lease_until=None, reconcile_error='')
    except Exception as error:
        code = error.code if isinstance(error, MetaFailure) else 'reconciliation_temporarily_unavailable'
        IntakeForm.objects.filter(pk=form.pk, reconcile_lease_until=lease).update(reconcile_lease_until=None, reconcile_error=code)
        if isinstance(error, MetaFailure) and error.pause:
            Connection.objects.filter(pk=form.connection_id).update(paused_reason=code)


@shared_task(ignore_result=True)
def enrich_campaign(receipt_id):
    receipt = Submission.objects.select_related('connection').get(pk=receipt_id)
    if not settings.INTAKE_ENABLED or not receipt.connection.enabled or receipt.connection.paused_reason:
        return
    campaign_id = receipt.attribution.get('campaign_id')
    if not campaign_id or receipt.mapped_values.get('campaign'):
        return
    try:
        payload = graph(receipt.connection, campaign_id, {'fields': 'name'})
        name = payload.get('name')
        if isinstance(name, str) and len(name) <= 160:
            Submission.objects.filter(pk=receipt.pk).update(campaign_name=name)
    except MetaFailure:
        pass


@shared_task(ignore_result=True)
def purge_expired_answers():
    from uploads.models import UploadBatch
    from uploads.storage import delete_paths
    cutoff = timezone.now() - timedelta(days=30)
    for receipt_id in Submission.objects.filter(received_at__lte=cutoff, answers_expired=False).exclude(state__in=TERMINAL).values_list('pk', flat=True).iterator():
        with transaction.atomic():
            receipt = Submission.objects.select_for_update(no_key=True).get(pk=receipt_id)
            if receipt.state in TERMINAL or receipt.answers_expired:
                continue
            receipt.answers = []
            receipt.corrections = {}
            receipt.mapped_values = {}
            receipt.normalized_phone = ''
            receipt.answers_expired = True
            receipt.lease_until = None
            receipt.lease_token = None
            receipt.next_attempt_at = None
            receipt.state = Submission.State.NEEDS_REVIEW
            receipt.review_reason = 'expired'
            receipt.errors = {'input': 'Answers expired. Supply corrected customer input before retry.'}
            receipt.save()
            record(receipt, 'answers_expired')
    # Row retention is independent of file deletion (files are deleted after parsing).
    for batch_id in UploadBatch.objects.filter(created_at__lte=cutoff).exclude(status='COMMITTED').filter(
        Q(rows__answers_expired=False) | Q(status='PARSING')
    ).values_list('pk', flat=True).distinct().iterator():
        with transaction.atomic():
            batch = UploadBatch.objects.select_for_update().get(pk=batch_id)
            if batch.status == 'COMMITTED':
                continue
            batch.rows.filter(answers_expired=False).update(answers=[], data={}, normalized_phone='', validation_error='Answers expired. Supply corrected input.', validation_errors={'input': 'Answers expired. Supply corrected input.'}, answers_expired=True)
            batch.status = UploadBatch.Status.READY
            batch.save(update_fields=['status'])
    for batch_id in UploadBatch.objects.filter(original_deleted_at__isnull=True).filter(Q(created_at__lte=cutoff) | Q(status__in=['READY', 'COMMITTED'])).values_list('pk', flat=True).iterator():
        from uploads.tasks import delete_original
        delete_original(batch_id)
