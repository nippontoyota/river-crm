"""Manual Meta test; optional existing-test correction uses the CRM review service."""
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
    from intake.models import IntakeForm, Submission
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
        user_token = settings.INTAKE_SECRETS[form.connection.secret_ref].get('user_access_token')
        existing_phone = Lead.objects.filter(phone=PHONE).exists()
        replace_test_id = os.environ.get('REPLACE_META_TEST_ID', '').strip()
        if replace_test_id and (not replace_test_id.isascii() or not replace_test_id.isdigit()
                or not Submission.objects.filter(external_id=replace_test_id, form=form,
                                                 fetched_at__isnull=False, answers_expired=False).exists()):
            raise ValueError('replacement_requires_retained_crm_receipt')

    def request(path, params, *, create=False, delete=False):
        # Fixed Meta host, no redirects, bounded response; secrets stay in headers.
        url = f'https://graph.facebook.com/{settings.META_GRAPH_VERSION}/{path}'
        encoded = urlencode(params)
        headers = {'Authorization': f'Bearer {user_token if delete and user_token else token}'}
        if create:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = Request(url if create else url + '?' + encoded,
                      data=encoded.encode() if create else None, headers=headers,
                      method='DELETE' if delete else ('POST' if create else 'GET'))
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
                detail = {}
            print(f'FAIL Meta HTTP={error.code} code={code if isinstance(code, int) else "redacted"} subcode={subcode if isinstance(subcode, int) else "redacted"}')
            # Only fixed diagnostic words, never Meta's free-text message or values.
            message = str(detail.get('message', '')).lower()
            words = ('invalid', 'user', 'id', 'page', 'access', 'token', 'test', 'lead',
                     'already', 'exists', 'permission', 'application', 'created', 'delete', 'unsupported')
            print('FAIL error_keywords=' + json.dumps([word for word in words if re.search(r'\b' + word + r'\b', message)]))
            raise ValueError('meta_request_failed') from None

    ownership = request(FORM_ID, {'fields': 'id,page,questions'})
    if str(ownership.get('page', {}).get('id')) != PAGE_ID:
        raise ValueError('page_mismatch')
    keys = {question.get('key') for question in ownership.get('questions', [])}
    print('PASS form ownership; question_keys=' + json.dumps(sorted(key for key in keys if isinstance(key, str))))
    print('INFO optional_user_token_configured=' + str(bool(user_token)).lower())

    # Reuse our own test on reruns. Existing tests are never deleted.
    tests = request(f'{FORM_ID}/test_leads', {'fields': 'id,field_data', 'limit': 10})
    review_id = os.environ.get('REVIEW_EXISTING_META_TEST_ID', '').strip()
    if review_id:
        if replace_test_id or not review_id.isascii() or not review_id.isdigit() or review_id not in {
                str(test.get('id', '')) for test in tests.get('data', [])}:
            raise ValueError('review_requires_confirmed_meta_test')
        from intake.services import record, resolve
        with transaction.atomic():
            receipt = Submission.objects.select_for_update().get(form=form, external_id=review_id)
            if receipt.state == 'IMPORTED' and receipt.lead.name.startswith(PREFIX):
                print(f'PASS existing reviewed Meta test CRM lead_id={receipt.lead_id}; meta_lead_id={review_id}')
                return
            if receipt.state != 'NEEDS_REVIEW' or not receipt.fetched_at or receipt.answers_expired or existing_phone:
                raise ValueError('review_test_not_eligible')
            name = PREFIX + datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ') + ' - DO NOT CONTACT'
            record(receipt, 'automation_test_review')
            receipt = resolve(receipt.pk, 'correct', actor=None, corrections={
                'name': name, 'phone': PHONE, 'email': 'meta-automation-test@example.com', 'city': 'Kochi',
            })
            if receipt.state != 'IMPORTED':
                raise ValueError('review_test_not_imported')
        print(f'PASS reviewed existing Meta test CRM lead_id={receipt.lead_id}; meta_lead_id={review_id}; status=FRESH')
        print('TEST NAME: ' + name)
        print('Existing Meta test fetched by Actions, then corrected through standard CRM review; no new Meta submission.')
        return
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
        existing_ids = [str(test.get('id', '')) for test in tests['data']]
        print('INFO existing Meta test ids=' + json.dumps([
            test_id for test_id in existing_ids if test_id.isascii() and test_id.isdigit()]))
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
    if replace_test_id:
        if [str(test.get('id', '')) for test in tests.get('data', [])] != [replace_test_id]:
            raise ValueError('replacement_test_id_mismatch')
        if request(replace_test_id, {}, delete=True).get('success') is not True:
            raise ValueError('test_deletion_not_confirmed')
        print(f'PASS replaced Meta test slot lead_id={replace_test_id}; existing CRM receipt retained')
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
                      'page_mismatch', 'invalid_test_id',
                      'dummy_phone_already_in_crm', 'form_questions_require_test_mapping',
                      'test_mapping_invalid', 'test_creation_not_confirmed',
                      'replacement_requires_retained_crm_receipt', 'replacement_test_id_mismatch',
                      'test_deletion_not_confirmed', 'review_requires_confirmed_meta_test',
                      'review_test_not_eligible', 'review_test_not_imported'}
        code = str(error) if isinstance(error, ValueError) and str(error) in safe_codes else 'meta_test_failed'
        print('FAIL ' + code + '; details redacted')
        sys.exit(1)
