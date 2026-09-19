"""Manual production smoke test: create one labelled Meta test lead, never a CRM row."""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

FORM_ID = '1237696338502111'
PAGE_ID = '1140811825785084'
PREFIX = 'AUTOMATION TEST - GitHub '
PHONE = '0000000000'


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    logging.disable(logging.CRITICAL)
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection, transaction
    from intake.mapping import map_entries, sanitize_entries
    from intake.meta import NoRedirect
    from intake.models import IntakeForm
    from leads.models import Lead

    if connection.vendor != 'postgresql' or not re.fullmatch(r'v[0-9]+\.0', settings.META_GRAPH_VERSION):
        raise ValueError('invalid_runtime')
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
        form = IntakeForm.objects.select_related('connection').get(
            external_id=FORM_ID, page_id=PAGE_ID, enabled=True,
            connection__enabled=True, connection__paused_reason='', connection__secret_ref='main-meta',
        )
        mapping = form.mappings.order_by('-version').first()
        if not mapping:
            raise ValueError('mapping_required')
        token = settings.INTAKE_SECRETS[form.connection.secret_ref]['access_token']
        existing_phone = Lead.objects.filter(phone=PHONE).exists()

    def request(path, params, *, create=False):
        # Fixed Meta host, no redirects, bounded response; secrets stay in headers.
        url = f'https://graph.facebook.com/{settings.META_GRAPH_VERSION}/{path}'
        encoded = urlencode(params)
        headers = {'Authorization': f'Bearer {token}'}
        if create:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = Request(url if create else url + '?' + encoded,
                      data=encoded.encode() if create else None, headers=headers)
        try:
            with build_opener(NoRedirect).open(req, timeout=30) as response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise ValueError('response_too_large')
                return json.loads(body)
        except HTTPError as error:
            try:
                detail = json.loads(error.read(65536)).get('error', {})
                code, subcode = detail.get('code'), detail.get('error_subcode')
            except (ValueError, AttributeError):
                code = subcode = None
            print(f'FAIL Meta HTTP={error.code} code={code if isinstance(code, int) else "redacted"} subcode={subcode if isinstance(subcode, int) else "redacted"}')
            raise ValueError('meta_request_failed') from None

    ownership = request(FORM_ID, {'fields': 'id,page,questions'})
    if str(ownership.get('page', {}).get('id')) != PAGE_ID:
        raise ValueError('page_mismatch')
    keys = {question.get('key') for question in ownership.get('questions', [])}
    print('PASS form ownership; question_keys=' + json.dumps(sorted(key for key in keys if isinstance(key, str))))

    # Meta may allow only one outstanding test per form. Never delete another test.
    tests = request(f'{FORM_ID}/test_leads', {'fields': 'id,field_data', 'limit': 10})
    for test in tests.get('data', []):
        name = next((str(field.get('values', [''])[0]) for field in test.get('field_data', [])
                     if field.get('name') == 'full_name' and field.get('values')), '')
        if name.startswith(PREFIX):
            test_id = str(test.get('id', ''))
            if not test_id.isascii() or not test_id.isdigit():
                raise ValueError('invalid_test_id')
            print(f'PASS reuse labelled Meta test lead_id={test_id}; awaiting normal importer')
            return
    if tests.get('data'):
        raise ValueError('existing_meta_test_requires_review')
    if existing_phone:
        raise ValueError('dummy_phone_already_in_crm')
    name = PREFIX + datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ') + ' - DO NOT CONTACT'
    values = {'full_name': name, 'phone_number': PHONE, 'email': 'meta-automation-test@example.com', 'city': 'Kochi'}
    if not set(values).issubset(keys):
        raise ValueError('form_questions_require_test_mapping')
    entries = [{'id': key, 'label': key, 'value': value} for key, value in values.items()]
    retained, _ = sanitize_entries(entries, mapping.rules)
    preview = map_entries(retained, mapping.rules)
    if preview['errors']:
        print('FAIL test mapping; review_fields=' + json.dumps(sorted(preview['errors'])))
        raise ValueError('test_mapping_invalid')
    payload = request(f'{FORM_ID}/test_leads', {'field_data': json.dumps([
        {'name': key, 'values': [value]} for key, value in values.items()
    ])}, create=True)
    test_id = str(payload.get('id', ''))
    if not test_id.isascii() or not test_id.isdigit():
        raise ValueError('test_creation_not_confirmed')
    print(f'PASS created Meta test lead_id={test_id}; form_id={FORM_ID}')
    print('TEST NAME: ' + name)
    print('No CRM insert or recovery request performed; wait for the normal Actions processor.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        safe_codes = {'invalid_runtime', 'mapping_required', 'response_too_large', 'meta_request_failed',
                      'page_mismatch', 'invalid_test_id', 'existing_meta_test_requires_review',
                      'dummy_phone_already_in_crm', 'form_questions_require_test_mapping',
                      'test_mapping_invalid', 'test_creation_not_confirmed'}
        code = str(error) if isinstance(error, ValueError) and str(error) in safe_codes else 'meta_test_failed'
        print('FAIL ' + code + '; details redacted')
        sys.exit(1)
