import uuid

from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import serializers

from .models import Booking


def _date(params, name, errors):
    raw = params.get(name, "").strip()
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        errors[name] = "Use the format YYYY-MM-DD."
    return value


def filter_admin_bookings(queryset, params):
    """Apply ?status=, ?date_from=, ?date_to=, ?customer= and ?business= filters.

    status: one of the Booking.Status values.
    date_from / date_to: inclusive YYYY-MM-DD, applied to start_at.
    customer: a numeric id filters by customer_id; any other value searches
              username, first_name and last_name case-insensitively.
    business: a UUID that filters by service__business_id; a malformed UUID
              returns 400; a valid but nonexistent UUID returns an empty set.
    """
    errors = {}

    status = params.get("status", "").strip()
    if status:
        if status not in Booking.Status.values:
            errors["status"] = "Not a valid booking status."
        else:
            queryset = queryset.filter(status=status)

    date_from = _date(params, "date_from", errors)
    date_to = _date(params, "date_to", errors)

    if not errors and date_from and date_to and date_from > date_to:
        errors["date_from"] = "date_from cannot be later than date_to."

    customer = params.get("customer", "").strip()

    business_raw = params.get("business", "").strip()
    business_id = None
    if business_raw:
        try:
            business_id = uuid.UUID(business_raw)
        except ValueError:
            errors["business"] = "Enter a valid business UUID."

    if errors:
        raise serializers.ValidationError(errors)

    if customer:
        if customer.isdigit():
            queryset = queryset.filter(customer_id=int(customer))
        else:
            queryset = queryset.filter(
                Q(customer__username__icontains=customer)
                | Q(customer__first_name__icontains=customer)
                | Q(customer__last_name__icontains=customer)
            )

    if business_id is not None:
        queryset = queryset.filter(service__business_id=business_id)

    if date_from:
        queryset = queryset.filter(start_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(start_at__date__lte=date_to)

    return queryset
