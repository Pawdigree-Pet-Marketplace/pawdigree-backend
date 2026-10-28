from decimal import Decimal, InvalidOperation

from django.db.models import Count, F, Q
from rest_framework import serializers

from .models import Pet

SORT_ORDERINGS = {
    "newest": ("-created_at", "-pet_id"),
    "age_asc": ("age", "-created_at"),
    "age_desc": ("-age", "-created_at"),
}
SORT_OPTIONS = ("newest", "popular", "price_asc", "price_desc", "age_asc", "age_desc")


def _values(params, name):
    """Read ?name=a&name=b and ?name=a,b the same way."""
    values = []
    for raw in params.getlist(name):
        values.extend(part.strip() for part in raw.split(",") if part.strip())
    return values


def _choice(params, name, allowed, errors):
    value = params.get(name, "").strip().upper()
    if not value:
        return None
    if value in allowed:
        return value
    errors[name] = f"Choose one of: {', '.join(allowed)}."
    return None


def _months(params, name, errors):
    raw = params.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        errors[name] = "Enter a whole number of months (0 or more)."
        return None
    return value


def _price(params, name, errors):
    raw = params.get(name, "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or value < 0:
        errors[name] = "Enter a price of 0 or more."
        return None
    return value


def _apply_sort(queryset, sort):
    if sort == "popular":
        # Popular = applied for by the most different customers.
        return queryset.annotate(
            application_count=Count(
                "adoption_applications__customer", distinct=True
            )
        ).order_by("-application_count", "-created_at", "-pet_id")
    if sort == "price_asc":
        return queryset.order_by(
            F("price").asc(nulls_last=True), "-created_at", "-pet_id"
        )
    if sort == "price_desc":
        return queryset.order_by(
            F("price").desc(nulls_last=True), "-created_at", "-pet_id"
        )
    return queryset.order_by(*SORT_ORDERINGS[sort])


def filter_public_pets(queryset, params):
    """Narrow and sort the public listing. Raises a 400 for bad values.

    Filters only narrow the queryset it is given, so hidden pets can never
    come back through a search.
    """
    errors = {}

    search = params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(breed__icontains=search)
            | Q(species__icontains=search)
            | Q(description__icontains=search)
        )

    breed = params.get("breed", "").strip()
    if breed:
        queryset = queryset.filter(breed__iexact=breed)

    species = _values(params, "species")
    if species:
        match = Q()
        for value in species:
            match |= Q(species__iexact=value)
        queryset = queryset.filter(match)

    vendor = params.get("vendor", "").strip()
    if vendor:
        queryset = queryset.filter(business__name__icontains=vendor)

    locations = _values(params, "location")
    if locations:
        match = Q()
        for value in locations:
            match |= Q(business__city_district__iexact=value)
        queryset = queryset.filter(match)

    gender = _choice(params, "gender", Pet.Gender.values, errors)
    if gender:
        queryset = queryset.filter(gender=gender)

    listing_type = _choice(params, "listing_type", Pet.ListingType.values, errors)
    if listing_type:
        queryset = queryset.filter(listing_type=listing_type)

    age_min = _months(params, "age_min", errors)
    age_max = _months(params, "age_max", errors)
    if age_min is not None and age_max is not None and age_min > age_max:
        errors["age_min"] = "age_min cannot be greater than age_max."

    price_min = _price(params, "price_min", errors)
    price_max = _price(params, "price_max", errors)
    if price_min is not None and price_max is not None and price_min > price_max:
        errors["price_min"] = "price_min cannot be greater than price_max."

    sort = params.get("sort", "").strip().lower()
    if sort and sort not in SORT_OPTIONS:
        errors["sort"] = f"Choose one of: {', '.join(SORT_OPTIONS)}."

    if errors:
        raise serializers.ValidationError(errors)

    if age_min is not None:
        queryset = queryset.filter(age__gte=age_min)
    if age_max is not None:
        queryset = queryset.filter(age__lte=age_max)
    # Pets with no price (adoption listings) drop out of price filters.
    if price_min is not None:
        queryset = queryset.filter(price__gte=price_min)
    if price_max is not None:
        queryset = queryset.filter(price__lte=price_max)

    if sort:
        queryset = _apply_sort(queryset, sort)

    return queryset


def public_locations():
    """Towns that currently have at least one public pet, A to Z."""
    return list(
        Pet.objects.publicly_visible()
        .order_by("business__city_district")
        .values_list("business__city_district", flat=True)
        .distinct()
    )