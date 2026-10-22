"""Compare configured labels without rewriting historical data or integration keys."""
from django.db.models import Q, Value
from django.db.models.functions import Trim
from django.db.models.lookups import IExact


def choice_key(value):
    return str(value or "").strip().casefold()


def matching_choice(value, options):
    key = choice_key(value)
    return next((str(option).strip() for option in options if choice_key(option) == key), "")


def unique_choices(options):
    values = {}
    for option in options:
        if key := choice_key(option):
            values.setdefault(key, str(option).strip())
    return list(values.values())


def choice_q(field, value):
    return Q(IExact(Trim(field), Value(str(value or "").strip())))


def activity_children(lists, activity):
    return unique_choices(child for parent, children in lists.get("subActivities", {}).items()
                          if choice_key(parent) == choice_key(activity) for child in children)


def merge_choice_counts(rows, field, options=()):
    """Merge count-only aggregates before callers calculate rates."""
    groups = {}
    for row in rows:
        key = choice_key(row[field])
        group = groups.setdefault(key, {field: matching_choice(row[field], options) or str(row[field] or "").strip()})
        for name, count in row.items():
            if name != field:
                group[name] = group.get(name, 0) + count
    return sorted(groups.values(), key=lambda row: (-row.get("total", 0), choice_key(row[field])))


NO_COLOR_PREFERENCE = "No Preference"
MISSING_COLOR_LABELS = {"", "color not set", "colour not set"}


def color_choices(options):
    return unique_choices([NO_COLOR_PREFERENCE, *[value for value in options
        if choice_key(value) not in MISSING_COLOR_LABELS | {choice_key(NO_COLOR_PREFERENCE)}]])


def color_q(field, value):
    if choice_key(value) == choice_key(NO_COLOR_PREFERENCE):
        result = Q(**{field + "__isnull": True})
        for label in (*MISSING_COLOR_LABELS, NO_COLOR_PREFERENCE):
            result |= choice_q(field, label)
        return result
    return choice_q(field, value)
