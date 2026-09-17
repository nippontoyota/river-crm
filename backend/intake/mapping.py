"""Customer-only mapping, shared by integrations and reviewed spreadsheets.

Entry IDs are original labels for JSON, column:N for spreadsheets, and field:N
for Meta. Lists preserve duplicate labels; no normalized dictionary can lose data.
"""
import re
from datetime import date, datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from leads.models import Lead, SystemConfig
from leads.serializers import configured_source
from leads.rtos import normalize_rto

FIELDS = ('name', 'phone', 'email', 'model_interest', 'city', 'pincode', 'rto', 'profession', 'branch', 'enquiry_date', 'campaign', 'source_label', 'activity', 'sub_activity')
COMPONENTS = ('first_name', 'last_name')


def normalize_label(value):
    return ''.join(c for c in str(value).casefold() if c.isalnum())


ALIASES = {normalize_label(f): f for f in FIELDS}
for destination, names in {
    'name': ['Name', 'Full Name', 'Customer Name'],
    'phone': ['Phone', 'Ph No:', 'Phone Number', 'phone_number', 'Mobile', 'Mobile No', 'Contact Number', 'Phone Nnumber'],
    'email': ['Email', 'E-mail', 'Email Address'],
    'model_interest': ['Model', 'Vehicle Interest', 'Interested Model', 'Model / Vehicle Interest'],
    'city': ['City', 'Town'], 'profession': ['Profession', 'Occupation'],
    'rto': ['RTO Name', 'RTO / SRTO', 'RTO Code', 'RTO Information', 'Regional Transport Office'],
    'enquiry_date': ['Enquiry Date', 'Inquiry Date'],
}.items():
    ALIASES.update({normalize_label(name): destination for name in names})
PROHIBITED = {normalize_label(f.name) for f in Lead._meta.fields if f.name not in FIELDS} | {
    'owner', 'ownerid', 'assignedsoid', 'assignedpsid', 'generatedbyid', 'psofficerid',
    'metadata', 'url', 'websiteurl', 'pageurl', 'referrer', 'password', 'secret', 'token',
}


def normalize_phone(value):
    raw = str(value or '').strip()
    if not re.fullmatch(r'\+?[0-9\s().-]+', raw):
        return ''
    digits = re.sub(r'[^0-9]', '', raw)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits if len(digits) == 10 else ''


def string(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def destination(entry, rules, excel=False):
    label = normalize_label(entry['label'])
    if label in PROHIBITED and not (excel and label == 'source'):
        return 'ignore'
    fields = rules.get('fields', {})
    if entry['id'] in fields:
        return fields[entry['id']]
    if entry['label'] in fields:
        return fields[entry['label']]
    if excel and label in {'location', 'date', 'source'}:
        return {'location': 'city', 'date': 'enquiry_date', 'source': 'source'}[label]
    return ALIASES.get(label, '')


def sanitize_entries(entries, rules, excel=False):
    retained, ignored = [], []
    for entry in entries:
        if destination(entry, rules, excel) == 'ignore':
            ignored.append(entry['label'])
        else:
            retained.append({**entry, 'value': string(entry.get('value'))})
    return retained, ignored


def validate_rules(rules, excel=False):
    allowed = set(FIELDS) | ( {'source'} if excel else set())
    if not isinstance(rules, dict) or set(rules) - {'fields', 'defaults', 'value_aliases', 'primary', 'required'}:
        raise ValidationError({'rules': 'Use fields, defaults, value_aliases, primary and required only.'})
    for key in ('fields', 'defaults', 'value_aliases', 'primary'):
        if not isinstance(rules.get(key, {}), dict):
            raise ValidationError({'rules': f'{key} must be an object.'})
    if any(not isinstance(k, str) or not isinstance(v, str) or v not in allowed | set(COMPONENTS) | {'ignore'} for k, v in rules.get('fields', {}).items()):
        raise ValidationError({'rules': 'Choose an approved customer field, name component or ignore.'})
    if set(rules.get('defaults', {})) - allowed or any(v is not None and not isinstance(v, (str, int, float)) for v in rules.get('defaults', {}).values()):
        raise ValidationError({'rules': 'Defaults must contain customer fields and scalar values only.'})
    if set(rules.get('primary', {})) - allowed - set(COMPONENTS) or any(not isinstance(v, str) for v in rules.get('primary', {}).values()):
        raise ValidationError({'rules': 'Primary choices must refer to an incoming entry ID.'})
    for key, aliases in rules.get('value_aliases', {}).items():
        if key not in allowed or not isinstance(aliases, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()):
            raise ValidationError({'rules': 'Value aliases must map strings to strings for customer fields.'})
    required = rules.get('required', [])
    if not isinstance(required, list) or any(not isinstance(v, str) or v not in allowed for v in required):
        raise ValidationError({'rules': 'Required mappings must be approved customer fields.'})
    return rules


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        result = value
    else:
        result = None
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                result = datetime.strptime(str(value), fmt).date()
                break
            except ValueError:
                pass
        if result is None:
            raise ValueError('Use a valid ISO or day-first enquiry date.')
    if result > timezone.localdate():
        raise ValueError('Enquiry date cannot be in the future.')
    return result.isoformat()


def validate_customer(values, excel=False):
    allowed = FIELDS + (('source',) if excel else ())
    data = {key: string(values.get(key)) for key in allowed}
    rto = normalize_rto(data['rto'])
    if rto is not None:
        data['rto'] = rto
    errors = {}
    if not data['name']:
        errors['name'] = 'Name is required.'
    phone = normalize_phone(data['phone'])
    if not phone:
        errors['phone'] = 'Enter a valid ten-digit phone number.'
    else:
        data['phone'] = phone
    for key in allowed:
        field = Lead._meta.get_field(key)
        if field.max_length and len(data[key]) > field.max_length:
            errors[key] = f'Maximum length is {field.max_length} characters.'
    if data['email']:
        try:
            validate_email(data['email'])
        except DjangoValidationError:
            errors['email'] = 'Enter a valid email address.'
    try:
        Lead._meta.get_field('pincode').run_validators(data['pincode'])
    except DjangoValidationError as error:
        errors['pincode'] = error.messages[0]
    try:
        data['enquiry_date'] = parse_date(data['enquiry_date'])
    except ValueError as error:
        errors['enquiry_date'] = str(error)  # Static messages; never include the supplied value.
    if data['rto'] and data['rto'] not in dict(Lead._meta.get_field('rto').choices):
        errors['rto'] = 'RTO could not be matched unambiguously. Use an approved code or office name, such as KL-05 or Kottayam.'
    lists = SystemConfig.objects.filter(pk=1).values_list('lists', flat=True).first() or {}
    for field, name in (('model_interest', 'models'), ('activity', 'activities'), ('branch', 'branches')):
        if data[field]:
            options = lists.get(name, [])
            if not options:
                errors[field] = f'Configuration required: add {name} in Admin Lists.'
            elif data[field] not in options:
                errors[field] = f'Choose an approved option from {name} in Admin Lists.'
    if data['sub_activity']:
        options = lists.get('subActivities', {}).get(data['activity'], [])
        if not options:
            errors['sub_activity'] = 'Configuration required: add sub-activities for the selected activity.'
        elif data['sub_activity'] not in options:
            errors['sub_activity'] = 'Choose a sub-activity belonging to the selected activity.'
    if excel:
        source = configured_source(data['source'])
        if not source:
            errors['source'] = 'Choose a lead source from Admin Lists.'
        else:
            data['source'] = source
    return data, errors


def equivalent(field, value):
    if field == 'rto':
        return normalize_rto(value) or value.casefold()
    if field == 'phone':
        return normalize_phone(value) or value.casefold()
    if field == 'enquiry_date':
        try:
            return parse_date(value)
        except ValueError:
            pass
    return ' '.join(value.casefold().split())


def map_entries(entries, rules=None, excel=False, corrections=None):
    rules = rules or {}
    candidates, preview, errors = {}, [], {}
    for entry in entries:
        target = destination(entry, rules, excel)
        value = string(entry.get('value'))
        aliases = rules.get('value_aliases', {}).get(target, {})
        value = next((v for k, v in aliases.items() if equivalent(target, k) == equivalent(target, value)), value)
        preview.append({'id': entry['id'], 'label': entry['label'], 'sample': '' if target == 'ignore' else value, 'destination': target})
        if target and target != 'ignore':
            candidates.setdefault(target, []).append((entry['id'], value))
    data = {}
    for field in set(candidates) | set(rules.get('primary', {})):
        items = candidates.get(field, [])
        primary = rules.get('primary', {}).get(field)
        if primary is not None:
            selected = next((value for key, value in items if key == primary), None)
            if selected is None or not selected:
                errors[field] = 'The saved primary field is missing or blank.'
            data[field] = selected or ''
        else:
            populated = [value for _, value in items if value]
            if len({equivalent(field, value) for value in populated}) > 1:
                errors[field] = 'Different incoming values target this field. Choose a primary field or correct it.'
            data[field] = populated[0] if populated else ''
    if not data.get('name'):
        data['name'] = ' '.join(data.get(key, '') for key in COMPONENTS if data.get(key))
        for key in COMPONENTS:
            if key in errors:
                errors['name'] = errors[key]
    errors = {key: value for key, value in errors.items() if key not in COMPONENTS}
    for field, default in rules.get('defaults', {}).items():
        if not data.get(field) and field not in errors:
            data[field] = string(default)
    for field, value in (corrections or {}).items():
        if field in FIELDS or (excel and field == 'source'):
            data[field] = value
            errors.pop(field, None)
    for field in rules.get('required', []):
        if not data.get(field):
            errors[field] = 'This configured required mapping is missing.'
    validated, validation_errors = validate_customer(data, excel)
    errors.update(validation_errors)
    return {'values': validated, 'errors': errors, 'entries': preview}
