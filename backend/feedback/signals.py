from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User
from .services import reconcile_assignments


@receiver(post_save, sender=User)
def feedback_staff_changed(sender, instance, raw=False, **kwargs):
    if not raw and instance.role == "FEEDBACK":
        transaction.on_commit(reconcile_assignments)
