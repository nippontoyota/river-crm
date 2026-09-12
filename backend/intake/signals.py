import time
from celery.signals import heartbeat_sent, worker_ready
from django.db import close_old_connections
from django.utils import timezone

_last_worker_heartbeat = 0


@heartbeat_sent.connect
def worker_heartbeat(**kwargs):
    global _last_worker_heartbeat
    if time.monotonic() - _last_worker_heartbeat < 20:
        return
    _last_worker_heartbeat = time.monotonic()
    try:
        close_old_connections()
        from .models import Heartbeat
        Heartbeat.objects.update_or_create(name='worker', defaults={'seen_at': timezone.now()})
    except Exception:
        pass
    finally:
        close_old_connections()


@worker_ready.connect
def recover_on_startup(**kwargs):
    from .services import publish
    from .tasks import purge_expired_answers, reconcile_forms, sweep_receipts
    for task in (purge_expired_answers, sweep_receipts, reconcile_forms):
        publish(task)
