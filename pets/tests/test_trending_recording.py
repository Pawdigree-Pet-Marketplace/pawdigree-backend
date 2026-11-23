import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from pets.models import Pet, PetSearchTerm

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_pet(vendor, vendor_business):
    def make(name="Buddy", **overrides):
        data = {
            "vendor": vendor,
            "business": vendor_business,
            "listing_type": Pet.ListingType.ADOPTION,
            "name": name,
            "species": "Dog",
            "breed": "Labrador",
            "age": 12,
            "gender": Pet.Gender.MALE,
            "size": Pet.Size.MEDIUM,
            "description": "Friendly and playful.",
            "approved": True,
        }
        data.update(overrides)
        return Pet.objects.create(**data)

    return make


def search(term, **extra):
    return APIClient().get(reverse("pet-public-list"), {"search": term, **extra})


def test_search_with_results_is_recorded_once(make_pet):
    make_pet()

    response = search("  Labrador ")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert PetSearchTerm.objects.get(term="labrador").count == 1


def test_repeat_searches_add_up(make_pet):
    make_pet()

    search("labrador")
    search("LABRADOR")

    assert PetSearchTerm.objects.get(term="labrador").count == 2


def test_search_with_no_results_is_not_recorded(make_pet):
    make_pet()

    response = search("zebra")

    assert response.json()["count"] == 0
    assert PetSearchTerm.objects.count() == 0


def test_browsing_without_a_search_is_not_recorded(make_pet):
    make_pet()

    response = APIClient().get(reverse("pet-public-list"))

    assert response.status_code == 200
    assert PetSearchTerm.objects.count() == 0


def test_second_page_is_not_counted_again(make_pet):
    make_pet("Buddy")
    make_pet("Rex")

    first = search("labrador", page_size=1)
    second = search("labrador", page_size=1, page=2)

    assert first.status_code == 200
    assert second.status_code == 200
    assert PetSearchTerm.objects.get(term="labrador").count == 1
