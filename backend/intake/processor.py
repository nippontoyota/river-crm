"""Short, brokerless runs over the existing durable receipt and upload queues."""
import signal
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .meta import MetaFailure, form_lead_page
from .models import Connection, Heartbeat, IntakeForm, Submission
from .services import accept
from .tasks import due_receipts, process_submission, purge_expired_answers


PROCESSOR_INTERVAL_SECONDS = 300
META_SCAN_INTERVAL_SECONDS = 1800
PROCESSOR_STALE_SECONDS = 900
META_SCAN_STALE_SECONDS = 3600


def request_due_scans():
    now = timezone.now()
    return IntakeForm.objects.filter(
        enabled=True, connection__enabled=True, connection__paused_reason='', connection__origin='META',
        activated_at__lte=now, connection__activated_at__lte=now, fetch_requested_at__isnull=True,
    ).filter(
        Q(last_reconciled_at__isnull=True) |
        Q(last_reconciled_at__lte=now - timedelta(seconds=META_SCAN_INTERVAL_SECONDS)) |
        Q(reconcile_end__isnull=False)
    ).update(fetch_requested_at=now)


class ProcessingDeadline(BaseException):
    # Do not let task-level `except Exception` mark interrupted work as failed.
    pass


@contextmanager
def time_limit(seconds):
    def expired(*_):
        raise ProcessingDeadline()

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def fetch_page(form_id):
    """Commit a page and its cursor together; interrupted pages replay safely."""
    with transaction.atomic():
        form = IntakeForm.objects.select_for_update(of=('self',)).select_related('connection').get(pk=form_id)
        now = timezone.now()
        if not form.fetch_requested_at or not form.enabled or not form.connection.enabled or form.connection.paused_reason:
            return
        if form.reconcile_lease_until and form.reconcile_lease_until > now:
            return
        lease = now + timedelta(minutes=5)
        form.reconcile_lease_until = lease
        if not form.reconcile_end:
            form.reconcile_start = max(form.activated_at, form.connection.activated_at, (form.checkpoint or form.activated_at) - timedelta(minutes=30))
            form.reconcile_end = form.fetch_requested_at
        form.save(update_fields=['reconcile_lease_until', 'reconcile_start', 'reconcile_end'])
    try:
        leads, cursor = form_lead_page(form, form.reconcile_start, form.reconcile_end, form.reconcile_cursor)
        with transaction.atomic():
            current = IntakeForm.objects.select_for_update(of=('self',)).select_related('connection').get(pk=form_id)
            if current.reconcile_lease_until != lease or not current.enabled or not current.connection.enabled or current.connection.paused_reason:
                return
            for external_id, submitted in leads:
                accept(current, external_id, submitted_at=submitted)
            current.reconcile_cursor = cursor
            current.reconcile_error = ''
            if not cursor:
                current.checkpoint = current.reconcile_end
                # A retried scan may first finish an older interrupted window.
                if current.reconcile_end >= current.fetch_requested_at:
                    current.fetch_requested_at = None
                    current.last_reconciled_at = timezone.now()
                current.reconcile_start = current.reconcile_end = None
            current.save(update_fields=['checkpoint', 'reconcile_cursor', 'reconcile_error', 'fetch_requested_at', 'last_reconciled_at', 'reconcile_start', 'reconcile_end'])
        return len(leads)
    except Exception as error:
        code = error.code if isinstance(error, MetaFailure) else 'reconciliation_temporarily_unavailable'
        changes = {'reconcile_error': code}
        # Keep the request for the next run; never retry failures in a tight loop.
        # Expired/repeated cursors restart the same fixed window with identity deduplication.
        if code in ('meta_request_rejected', 'meta_invalid_pagination'):
            changes['reconcile_cursor'] = ''
        IntakeForm.objects.filter(pk=form_id, reconcile_lease_until=lease).update(**changes)
        if isinstance(error, MetaFailure) and error.pause:
            Connection.objects.filter(pk=form.connection_id).update(paused_reason=code)
        return None
    finally:
        IntakeForm.objects.filter(pk=form_id, reconcile_lease_until=lease).update(reconcile_lease_until=None)


def process_pending(max_seconds=240, *, automatic_meta=False, reminders=False):
    from uploads.models import UploadBatch
    from uploads.tasks import parse_upload_batch

    token = uuid.uuid4()
    with transaction.atomic():
        # ponytail: one processor per database; split queues only if measured backlog requires it.
        heartbeat, _ = Heartbeat.objects.get_or_create(name='processor')
        heartbeat = Heartbeat.objects.select_for_update().get(pk=heartbeat.pk)
        now = timezone.now()
        if heartbeat.lease_until and heartbeat.lease_until > now:
            return 'Another processor is running.'
        heartbeat.seen_at = now
        heartbeat.lease_until = now + timedelta(seconds=max_seconds + 30)
        heartbeat.lease_token = token
        heartbeat.save()
        Heartbeat.objects.update_or_create(name='processor_attempt', defaults={'seen_at': now})

    def beat():
        Heartbeat.objects.filter(name='processor', lease_token=token).update(seen_at=timezone.now())

    deadline = time.monotonic() + max_seconds
    started = now
    scanned = 0
    failed_forms = set()
    budget_reached = False
    try:
        with time_limit(max_seconds):
            if reminders:
                from feedback.tasks import process_feedback_queue
                from notifications.tasks import create_due_follow_up_notifications
                create_due_follow_up_notifications.run()
                process_feedback_queue.run()
            # Run due retention before scanning so a long catch-up cannot starve it.
            # Upload retention also runs when integration intake is disabled.
            if not Heartbeat.objects.filter(name='retention', seen_at__gt=timezone.now() - timedelta(hours=1)).exists():
                purge_expired_answers.run()
                Heartbeat.objects.update_or_create(name='retention', defaults={'seen_at': timezone.now()})
            scans_requested = False
            while time.monotonic() < deadline:
                did_work = False
                # Alternate queues so a large recovery scan cannot starve uploads or webhooks.
                batch_id = UploadBatch.objects.filter(status='PARSING', original_deleted_at__isnull=True).order_by('created_at', 'pk').values_list('pk', flat=True).first()
                if batch_id is not None:
                    parse_upload_batch.run(batch_id)
                    did_work = True
                    beat()
                if settings.INTAKE_ENABLED:
                    for receipt_id in list(due_receipts().values_list('pk', flat=True)[:20]):
                        process_submission.run(str(receipt_id))
                        did_work = True
                        beat()
                    if automatic_meta and not scans_requested:
                        request_due_scans()
                        scans_requested = True
                    forms = IntakeForm.objects.filter(fetch_requested_at__isnull=False, enabled=True, connection__enabled=True, connection__paused_reason='', connection__origin='META').filter(
                        Q(reconcile_lease_until__isnull=True) | Q(reconcile_lease_until__lte=timezone.now())
                    ).exclude(pk__in=failed_forms).order_by('fetch_requested_at', 'pk').values_list('pk', flat=True)[:100]
                    for form_id in list(forms):
                        result = fetch_page(form_id)
                        if result is None:
                            failed_forms.add(form_id)
                        else:
                            scanned += result
                        did_work = True
                        beat()
                if not did_work:
                    break
    except ProcessingDeadline:
        budget_reached = True
    finally:
        Heartbeat.objects.filter(name='processor', lease_token=token).update(seen_at=timezone.now(), lease_until=None, lease_token=None)
    # A clean budget yield is successful: durable in-flight work resumes next run.
    # Unhandled exceptions skip this heartbeat even though the lease is released.
    counts = dict(Submission.objects.values('state').annotate(total=Count('pk')).values_list('state', 'total'))
    imported = Submission.objects.filter(state='IMPORTED', updated_at__gte=started).count()
    pending_receipts = sum(counts.get(state, 0) for state in ('RECEIVED', 'PROCESSING'))
    pending_scans = IntakeForm.objects.filter(fetch_requested_at__isnull=False).count()
    pending_uploads = UploadBatch.objects.filter(status='PARSING').count()
    summary = (
        f'scanned={scanned} imported={imported} awaiting_review={counts.get("NEEDS_REVIEW", 0)} '
        f'failed={counts.get("FAILED", 0)} scan_failures={len(failed_forms)} '
        f'upload_failures={UploadBatch.objects.filter(status="FAILED").count()} '
        f'remaining_receipts={pending_receipts} remaining_scans={pending_scans} remaining_uploads={pending_uploads}'
    )
    Heartbeat.objects.update_or_create(name='processor_success', defaults={'seen_at': timezone.now()})
    return ('Time budget reached; remaining work will resume on the next run. ' if budget_reached else 'Processing completed. ') + summary
