"""Read-only preflight. Never print tokens, answers, mapping values or exception text."""
import re

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from intake.mapping import map_entries, sanitize_entries
from intake.meta import MetaFailure, fetch_lead, form_lead_page, graph
from intake.models import IntakeForm, Submission


class Command(BaseCommand):
    help = 'Read-only database, configuration, Meta ownership, lead access and mapping checks. No imports.'

    def add_arguments(self, parser):
        parser.add_argument('--secret-ref', default='main-meta')

    def handle(self, *args, **options):
        try:
            self.check_configuration(options['secret_ref'])
            with transaction.atomic():
                if connection.vendor == 'postgresql':
                    with connection.cursor() as cursor:
                        cursor.execute('SET TRANSACTION READ ONLY')
                        self.check_permissions(cursor)
                else:
                    self.stdout.write('SKIP database_permissions: PostgreSQL required for production verification.')
                self.check_meta(options['secret_ref'])
        except CommandError as error:
            self.stdout.write(f'FAIL {error}')
            raise
        except MetaFailure as error:
            self.stdout.write(f'FAIL {error.code}')
            raise CommandError(error.code) from None
        except Exception:
            raise CommandError('preflight_failed; check database connectivity and configuration. Details redacted.') from None

    def check_configuration(self, secret_ref):
        config = settings.INTAKE_SECRETS.get(secret_ref, {})
        checks = {
            'DJANGO_SECRET_KEY': bool(settings.SECRET_KEY and settings.SECRET_KEY != 'development-only-change-me'),
            'INTAKE_SECRETS_JSON.access_token': bool(config.get('access_token')),
            'META_APP_SECRET': bool(settings.META_APP_SECRET),
            'META_VERIFY_TOKEN': bool(settings.META_VERIFY_TOKEN),
            'META_GRAPH_VERSION': bool(re.fullmatch(r'v[0-9]+\.0', settings.META_GRAPH_VERSION)),
            'SUPABASE_URL': bool(settings.SUPABASE_URL),
            'SUPABASE_SECRET_KEY': bool(settings.SUPABASE_SECRET_KEY),
            'SUPABASE_UPLOAD_BUCKET': bool(settings.SUPABASE_BUCKET),
            'JWT_SIGNING_KEY': bool(settings.SIMPLE_JWT['SIGNING_KEY']),
            'INTAKE_FINGERPRINT_KEY': bool(settings.INTAKE_FINGERPRINT_KEY),
            'INTAKE_EXECUTION_MODE': settings.INTAKE_EXECUTION_MODE == 'database',
            'INTAKE_ENABLED': settings.INTAKE_ENABLED,
            'CELERY_TASK_ALWAYS_EAGER': not settings.CELERY_TASK_ALWAYS_EAGER,
            'DJANGO_DEBUG': not settings.DEBUG,
        }
        for name, valid in checks.items():
            self.stdout.write(f'{"PASS" if valid else "FAIL"} configured {name}')
        if not all(checks.values()):
            raise CommandError('configuration_required')

    def check_permissions(self, cursor):
        # SELECT-only privilege probes; do not test writes by creating production rows.
        for model in apps.get_models():
            if model._meta.app_label not in {'intake', 'uploads', 'leads', 'accounts', 'notifications', 'feedback', 'ceo'}:
                continue
            table = model._meta.db_table
            for privilege in ('SELECT', 'INSERT', 'UPDATE'):
                cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, privilege])
                if not cursor.fetchone()[0]:
                    raise CommandError(f'database_permission_required: {table} {privilege}')
            cursor.execute('SELECT pg_get_serial_sequence(%s, %s)', [table, model._meta.pk.column])
            sequence = cursor.fetchone()[0]
            if sequence:
                cursor.execute('SELECT has_sequence_privilege(current_user, %s, %s)', [sequence, 'USAGE'])
                if not cursor.fetchone()[0]:
                    raise CommandError(f'database_sequence_permission_required: {table}')
        self.stdout.write('PASS database connectivity and table/sequence permissions')

    def check_meta(self, secret_ref):
        forms = list(IntakeForm.objects.select_related('connection').filter(
            connection__origin='META', connection__secret_ref=secret_ref,
            connection__enabled=True, enabled=True,
        ))
        if not forms:
            raise CommandError('enabled_meta_form_required')
        missing_sample = False
        for form in forms:
            ownership = graph(form.connection, form.external_id, {'fields': 'id,page'})
            if str(ownership.get('id', '')) != form.external_id or str(ownership.get('page', {}).get('id', '')) != form.page_id:
                raise MetaFailure('meta_form_ownership_mismatch', pause=True)
            self.stdout.write(f'PASS ownership page={form.page_id} form={form.external_id}')
            leads, _ = form_lead_page(form, max(form.activated_at, form.connection.activated_at), timezone.now(), limit=5)
            if not leads:
                self.stdout.write('PASS access succeeded; sample retrieval not yet demonstrated.')
                missing_sample = True
                continue
            # Unsaved model: reuse the exact fetch/validation path without accept() or tasks.
            sample = Submission(connection=form.connection, form=form, external_id=leads[0][0])
            fetched = fetch_lead(sample)
            if fetched is None:
                self.stdout.write('PASS access succeeded; sample retrieval not yet demonstrated.')
                missing_sample = True
                continue
            entries, _, _ = fetched
            mapping = form.mappings.order_by('-version').first()
            rules = mapping.rules if mapping else {}
            retained, _ = sanitize_entries(entries, rules)
            preview = map_entries(retained, rules)
            # JSON encoding prevents remote field labels from becoming log control sequences.
            import json
            self.stdout.write('PASS sample retrieval; fields=' + json.dumps(sorted({entry['label'] for entry in entries}), ensure_ascii=True))
            self.stdout.write('PASS mapping preview; review_fields=' + json.dumps(sorted(preview['errors']), ensure_ascii=True))
        if missing_sample:
            raise CommandError('sample_retrieval_not_demonstrated; activation gate remains closed.')
