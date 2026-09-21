"""Read-only preflight. Never print tokens, answers, mapping values or exception text."""
import json
import re

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from intake.mapping import map_entries, sanitize_entries
from intake.meta import MetaFailure, fetch_lead, form_lead_page, form_leads, graph
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
            entries, submitted_at, _ = fetched
            mapping = form.mappings.order_by('-version').first()
            rules = mapping.rules if mapping else {}
            retained, _ = sanitize_entries(entries, rules)
            preview = map_entries(retained, rules)
            # JSON encoding prevents remote field labels from becoming log control sequences.
            self.stdout.write('PASS sample retrieval; fields=' + json.dumps(sorted({entry['label'] for entry in entries}), ensure_ascii=True))
            self.stdout.write('PASS mapping preview; review_fields=' + json.dumps(sorted(preview['errors']), ensure_ascii=True))
            self.stdout.write('PASS sample submission time=' + timezone.localtime(submitted_at).isoformat())
        self.check_today(forms)
        if missing_sample:
            raise CommandError('sample_retrieval_not_demonstrated; activation gate remains closed.')

    def check_today(self, forms):
        """Compare live Meta IDs with saved receipts without fetching customer answers."""
        end = timezone.localtime()
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        self.stdout.write(f'PASS daily audit window={start.isoformat()}..{end.isoformat()}')
        pages = {(form.connection_id, form.page_id): form.connection for form in forms}
        for (connection_id, page_id), meta_connection in pages.items():
            discovered = {form.external_id for form in forms if form.connection_id == connection_id and form.page_id == page_id}
            cursor, seen = '', set()
            for _ in range(20):
                params = {'fields': 'id', 'limit': 100}
                if cursor:
                    params['after'] = cursor
                payload = graph(meta_connection, f'{page_id}/leadgen_forms', params)
                if not isinstance(payload.get('data'), list):
                    raise MetaFailure('meta_invalid_response')
                for item in payload['data']:
                    form_id = str(item.get('id', '')) if isinstance(item, dict) else ''
                    if not re.fullmatch(r'[0-9]{1,100}', form_id):
                        raise MetaFailure('meta_invalid_identifier')
                    discovered.add(form_id)
                paging = payload.get('paging', {})
                if not paging.get('next'):
                    break
                cursor = paging.get('cursors', {}).get('after')
                if not isinstance(cursor, str) or not cursor or len(cursor) > 4096 or cursor in seen:
                    raise MetaFailure('meta_invalid_pagination')
                seen.add(cursor)
            else:
                raise CommandError('meta_form_inventory_incomplete')
            self.stdout.write(f'PASS page inventory page={page_id} forms={len(discovered)}')
            for form_id in sorted(discovered):
                saved = IntakeForm.objects.filter(connection_id=connection_id, external_id=form_id).first()
                form = saved or IntakeForm(connection=meta_connection, page_id=page_id, external_id=form_id)
                leads = dict(form_leads(form, start, end))
                receipts = Submission.objects.filter(connection_id=connection_id, external_id__in=leads)
                states = {}
                for state in receipts.values_list('state', flat=True):
                    states[state] = states.get(state, 0) + 1
                report = {'page': page_id, 'form': form_id, 'enabled_in_crm': bool(saved and saved.enabled),
                          'meta_today': len(leads), 'missing_receipts': len(leads) - sum(states.values()),
                          'receipt_states': states,
                          'latest_today': timezone.localtime(max(leads.values())).isoformat() if leads else None}
                self.stdout.write('PASS daily comparison ' + json.dumps(report, sort_keys=True))
