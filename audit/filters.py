from django.utils.dateparse import parse_date
from rest_framework import serializers


def _date(params, name, errors):
    raw = params.get(name, '').strip()
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        errors[name] = 'Use the format YYYY-MM-DD.'
    return value


def filter_audit_logs(queryset, params):
    """Apply ?user=, ?action=, ?date_from= and ?date_to= to audit entries.

    user: an account id, or part of the actor's email.
    action: one action or a comma-separated list, e.g. pet.updated,pet.removed.
    date_from / date_to: inclusive, YYYY-MM-DD.
    """
    errors = {}

    user = params.get('user', '').strip()
    if user:
        if user.isdigit():
            queryset = queryset.filter(actor_id=int(user))
        else:
            queryset = queryset.filter(actor_email__icontains=user)

    actions = []
    for raw in params.getlist('action'):
        actions.extend(part.strip() for part in raw.split(',') if part.strip())
    if actions:
        queryset = queryset.filter(action__in=actions)

    date_from = _date(params, 'date_from', errors)
    date_to = _date(params, 'date_to', errors)

    if errors:
        raise serializers.ValidationError(errors)

    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    return queryset
