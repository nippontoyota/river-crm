"""Pinned Graph requests with fixed hosts, bounded bodies and redacted failures."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .services import secret_config


class MetaFailure(Exception):
    def __init__(self, code, pause=False, permanent=False):
        self.code, self.pause, self.permanent = code, pause, permanent
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def graph(connection, path, params):
    version = settings.META_GRAPH_VERSION
    token = secret_config(connection).get('access_token', '')
    if not re.fullmatch(r'v[0-9]+\.0', version) or not token:
        raise MetaFailure('meta_configuration_required', pause=True)
    if not re.fullmatch(r'[0-9]+(?:/(?:leads|leadgen_forms))?', path):
        raise MetaFailure('meta_invalid_identifier', permanent=True)
    url = f'https://graph.facebook.com/{version}/{path}?{urlencode(params)}'
    request = Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise MetaFailure('meta_response_too_large')
            payload = json.loads(body)
    except HTTPError as error:
        code = None
        try:
            code = json.loads(error.read(65536)).get('error', {}).get('code')
        except (ValueError, AttributeError):
            pass
        if code in (190, 10, 200, 294) or error.code in (401, 403):
            raise MetaFailure('meta_access_required', pause=True) from None
        if error.code == 429 or error.code >= 500 or code in (4, 17, 32, 613):
            raise MetaFailure('meta_temporarily_unavailable') from None
        raise MetaFailure('meta_request_rejected', permanent=True) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise MetaFailure('meta_temporarily_unavailable') from None
    if not isinstance(payload, dict) or 'error' in payload:
        raise MetaFailure('meta_invalid_response')
    return payload


def submitted_time(value):
    try:
        result = parse_datetime(value or '')
    except (ValueError, TypeError):
        result = None
    if not result or timezone.is_naive(result):
        raise MetaFailure('meta_invalid_submission_time', permanent=True)
    return result


def fetch_lead(receipt):
    form = receipt.form
    ownership = graph(receipt.connection, form.external_id, {'fields': 'id,page'})
    if str(ownership.get('page', {}).get('id', '')) != form.page_id:
        raise MetaFailure('meta_form_ownership_mismatch', pause=True)
    payload = graph(receipt.connection, receipt.external_id, {'fields': 'id,created_time,form_id,field_data,ad_id,adset_id,campaign_id'})
    if str(payload.get('id', '')) != receipt.external_id or str(payload.get('form_id', '')) != form.external_id:
        raise MetaFailure('meta_form_mismatch', permanent=True)
    submitted = submitted_time(payload.get('created_time'))
    if submitted < max(form.activated_at, receipt.connection.activated_at):
        return None
    if submitted > timezone.now():
        raise MetaFailure('meta_invalid_submission_time', permanent=True)
    entries = []
    raw_fields = payload.get('field_data', [])
    if not isinstance(raw_fields, list) or len(raw_fields) > 100:
        raise MetaFailure('meta_invalid_fields', permanent=True)
    for index, field in enumerate(raw_fields):
        if not isinstance(field, dict) or not isinstance(field.get('name'), str) or len(field['name']) > 160:
            raise MetaFailure('meta_invalid_fields', permanent=True)
        values = field.get('values', [])
        if not isinstance(values, list):
            raise MetaFailure('meta_invalid_fields', permanent=True)
        for offset, value in enumerate(values or ['']):
            if value is not None and not isinstance(value, (str, int, float)):
                raise MetaFailure('meta_invalid_fields', permanent=True)
            entries.append({'id': f'field:{index}:{offset}', 'label': field['name'], 'value': value})
    counts = {}
    labels = [entry['label'] for entry in entries]
    for entry in entries:
        label = entry['label']
        counts[label] = counts.get(label, 0) + 1
        entry['id'] = label if labels.count(label) == 1 else f'{label}#{counts[label]}'
    attribution = {'page_id': form.page_id, 'form_id': form.external_id, 'lead_id': receipt.external_id}
    for key in ('ad_id', 'adset_id', 'campaign_id'):
        value = str(payload.get(key, ''))
        if value.isascii() and value.isdigit() and len(value) <= 100:
            attribution[key] = value
    return entries, submitted, attribution


def form_lead_page(form, start, end, cursor=''):
    params = {'fields': 'id,created_time', 'limit': 100,
              'filtering': json.dumps([{'field': 'time_created', 'operator': 'GREATER_THAN', 'value': int(start.timestamp()) - 1}, {'field': 'time_created', 'operator': 'LESS_THAN', 'value': int(end.timestamp()) + 1}])}
    if cursor:
        params['after'] = cursor
    payload = graph(form.connection, f'{form.external_id}/leads', params)
    if not isinstance(payload.get('data'), list):
        raise MetaFailure('meta_invalid_response')
    leads = []
    for lead in payload['data']:
        if not isinstance(lead, dict):
            raise MetaFailure('meta_invalid_response')
        submitted = submitted_time(lead.get('created_time'))
        lead_id = str(lead.get('id', ''))
        if not lead_id.isascii() or not lead_id.isdigit() or len(lead_id) > 100:
            raise MetaFailure('meta_invalid_identifier')
        if start <= submitted <= end:
            leads.append((lead_id, submitted))
    paging = payload.get('paging', {})
    next_cursor = ''
    if paging.get('next'):
        next_cursor = paging.get('cursors', {}).get('after')
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor or len(next_cursor) > 4096:
            raise MetaFailure('meta_invalid_pagination')
    return leads, next_cursor  # Never follow a payload URL or expose a query-string token.


def form_leads(form, start, end):
    cursors = set()
    cursor = ''
    while True:
        leads, cursor = form_lead_page(form, start, end, cursor)
        yield from leads
        if not cursor:
            return
        if cursor in cursors:
            raise MetaFailure('meta_invalid_pagination')
        cursors.add(cursor)
