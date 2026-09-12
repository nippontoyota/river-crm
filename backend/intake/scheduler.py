import time
from celery.beat import PersistentScheduler
from django.db import close_old_connections
from django.utils import timezone


class HeartbeatScheduler(PersistentScheduler):
    last_heartbeat = 0

    def tick(self, *args, **kwargs):
        if time.monotonic() - self.last_heartbeat >= 20:
            try:
                close_old_connections()
                from .models import Heartbeat
                Heartbeat.objects.update_or_create(name='scheduler', defaults={'seen_at': timezone.now()})
                self.last_heartbeat = time.monotonic()
            except Exception:
                pass
            finally:
                close_old_connections()
        return min(super().tick(*args, **kwargs), 20)
