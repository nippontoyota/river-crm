from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.cache import caches
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.models import User, UserLifecycleEvent
from complaints.models import Complaint, ComplaintNote
from leads.models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig
from notifications.models import Notification
from uploads.models import UploadBatch, UploadRow
from uploads.storage import delete_paths


DELETE_MODELS = [
    UserLifecycleEvent,
    ComplaintNote,
    Notification,
    UploadRow,
    LeadQualification,
    CallLog,
    FollowUp,
    LeadAudit,
    Complaint,
    UploadBatch,
    Lead,
    SystemConfig,
    BlacklistedToken,
    OutstandingToken,
    Session,
    LogEntry,
    Group,
]


class Command(BaseCommand):
    help = "Permanently remove all CRM data except one existing admin account."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--delete-storage", action="store_true")
        parser.add_argument("--confirm-production-reset", action="store_true")

    def handle(self, *args, **options):
        email = options["admin_email"].strip().lower()
        matches = User.objects.filter(email__iexact=email)
        if matches.count() != 1:
            raise CommandError(f"Expected exactly one keeper account for {email}.")
        keeper = matches.get()
        if not (keeper.role == User.Role.ADMIN and keeper.is_active and keeper.is_staff and keeper.is_superuser):
            raise CommandError("Keeper must be an active ADMIN, staff member, and superuser.")

        counts = [(model._meta.label, model.objects.count()) for model in DELETE_MODELS]
        counts.append(("accounts.User (deleted)", User.objects.exclude(pk=keeper.pk).count()))
        storage_paths = list(UploadBatch.objects.exclude(storage_path="").values_list("storage_path", flat=True))
        self.stdout.write(f"Keeper: {keeper.email} (id={keeper.pk})")
        for label, count in counts:
            self.stdout.write(f"{label}: {count}")
        self.stdout.write(f"Storage objects: {len(storage_paths)}")

        if not options["confirm_production_reset"]:
            self.stdout.write(self.style.WARNING("Dry run only; no data was changed."))
            return
        if not options["delete_storage"]:
            raise CommandError("Confirmed resets require --delete-storage.")
        if storage_paths and connection.vendor == "postgresql" and not (settings.SUPABASE_URL and settings.SUPABASE_SECRET_KEY):
            raise CommandError("Supabase Storage credentials are required before the database can be reset.")

        delete_paths(storage_paths)
        password_hash = keeper.password
        with transaction.atomic():
            keeper = User.objects.select_for_update().get(pk=keeper.pk)
            for model in DELETE_MODELS:
                model.objects.all().delete()
            keeper.groups.clear()
            keeper.user_permissions.clear()
            User.objects.exclude(pk=keeper.pk).delete()
            if keeper.password != password_hash:
                raise CommandError("Keeper password changed during reset; transaction rolled back.")
            sql = connection.ops.sequence_reset_sql(no_style(), [*DELETE_MODELS, User])
            with connection.cursor() as cursor:
                for statement in sql:
                    cursor.execute(statement)

        try:
            caches["analytics"].clear()
        except Exception as error:
            self.stderr.write(self.style.WARNING(f"Analytics cache clear failed: {type(error).__name__}"))
        self.stdout.write(self.style.SUCCESS(f"Reset complete; retained only {keeper.email}."))
