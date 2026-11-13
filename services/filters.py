from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import serializers

from categories.models import Category


def _price(params, name, errors):
    raw = params.get(name, "").strip()
    if not raw:
        return None

    try:
        value = Decimal(raw)
    except InvalidOperation:
        value = None

    if value is None or not value.is_finite() or value < 0:
        errors[name] = "Enter a valid price of 0 or more."
        return None

    return value


def filter_public_services(queryset, params):
    """Apply customer filters without widening the given visible queryset."""
    errors = {}

    search = params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    category_id = params.get("category", "").strip()
    if category_id:
        try:
            category_id = int(category_id)
        except ValueError:
            category_id = 0

        category = Category.objects.filter(
            pk=category_id,
            is_active=True,
            kind__in=(Category.Kind.SERVICES, Category.Kind.GENERAL),
        ).first()
        if category is None:
            errors["category"] = (
                "Choose an active services or general category id."
            )
        else:
            queryset = queryset.filter(category_id=category.pk)

    city_district = params.get("city_district", "").strip()
    if city_district:
        queryset = queryset.filter(
            business__city_district__icontains=city_district
        )

    min_price = _price(params, "min_price", errors)
    max_price = _price(params, "max_price", errors)
    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        errors["min_price"] = "min_price cannot be greater than max_price."

    if errors:
        raise serializers.ValidationError(errors)

    if min_price is not None:
        queryset = queryset.filter(price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(price__lte=max_price)

    return queryset
