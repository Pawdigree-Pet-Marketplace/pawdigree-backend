from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from pets.models import PetSearchTerm

pytestmark = pytest.mark.django_db


def test_returns_most_searched_terms_first_without_login():
    PetSearchTerm.objects.create(term="labrador", count=5)
    PetSearchTerm.objects.create(term="persian cat", count=9)

    response = APIClient().get(reverse("pet-trending-searches"))

    assert response.status_code == 200
    assert response.json() == [
        {"term": "persian cat", "count": 9},
        {"term": "labrador", "count": 5},
    ]


def test_terms_not_searched_for_30_days_are_left_out():
    PetSearchTerm.objects.create(term="fresh", count=1)
    PetSearchTerm.objects.create(
        term="stale", count=50, last_searched_at=timezone.now() - timedelta(days=31)
    )

    response = APIClient().get(reverse("pet-trending-searches"))

    assert [row["term"] for row in response.json()] == ["fresh"]


def test_limit_is_respected_and_capped():
    for i in range(25):
        PetSearchTerm.objects.create(term=f"term {i}", count=i + 1)
    url = reverse("pet-trending-searches")

    assert len(APIClient().get(url).json()) == 8
    assert len(APIClient().get(url, {"limit": 3}).json()) == 3
    assert len(APIClient().get(url, {"limit": 500}).json()) == 20
    assert len(APIClient().get(url, {"limit": "abc"}).json()) == 8


def test_record_normalises_and_counts_terms():
    PetSearchTerm.record("  Labrador ")
    PetSearchTerm.record("LABRADOR")

    assert PetSearchTerm.objects.get(term="labrador").count == 2


def test_record_ignores_too_short_or_too_long_terms():
    PetSearchTerm.record("a")
    PetSearchTerm.record("x" * 61)

    assert PetSearchTerm.objects.count() == 0
