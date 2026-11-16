import pytest
from django.urls import reverse
from rest_framework import status

from pets.models import Pet
from pets.tests.test_public_and_admin import get_results, make_pet, pet_names

URL_NAME = "pet-admin-list"


@pytest.fixture
def listings(vendor, vendor_business, another_vendor, another_vendor_business):
    """One listing in every state an admin needs to see."""
    return {
        "approved": make_pet(vendor, vendor_business, "Approved Pet", approved=True),
        "pending": make_pet(vendor, vendor_business, "Pending Pet"),
        "rejected": make_pet(
            vendor, vendor_business, "Rejected Pet", rejection_reason="Blurry photos"
        ),
        "removed": make_pet(
            vendor, vendor_business, "Removed Pet", approved=True, is_active=False
        ),
        "other": make_pet(
            another_vendor,
            another_vendor_business,
            "Other Vendor Pet",
            approved=True,
            listing_type=Pet.ListingType.SALE,
            price="500000",
        ),
    }


def admin_get(api_client, user, **params):
    api_client.force_authenticate(user)
    return api_client.get(reverse(URL_NAME), params)


ALL_NAMES = {
    "Approved Pet",
    "Pending Pet",
    "Rejected Pet",
    "Removed Pet",
    "Other Vendor Pet",
}


@pytest.mark.django_db
def test_admin_sees_every_listing_in_every_state(api_client, admin, listings):
    response = admin_get(api_client, admin)

    assert response.status_code == status.HTTP_200_OK
    assert pet_names(response) == ALL_NAMES


@pytest.mark.django_db
def test_system_admin_sees_every_listing(api_client, system_admin, listings):
    response = admin_get(api_client, system_admin)

    assert response.status_code == status.HTTP_200_OK
    assert pet_names(response) == ALL_NAMES


@pytest.mark.django_db
def test_listing_shows_review_status_and_active_flag(api_client, admin, listings):
    response = admin_get(api_client, admin, review_status="rejected")

    item = get_results(response)[0]
    assert item["review_status"] == "REJECTED"
    assert item["rejection_reason"] == "Blurry photos"
    assert item["is_active"] is True


@pytest.mark.django_db
def test_customer_cannot_use_the_admin_list(api_client, customer, listings):
    response = admin_get(api_client, customer)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_vendor_cannot_use_the_admin_list(api_client, vendor, listings):
    response = admin_get(api_client, vendor)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_anonymous_cannot_use_the_admin_list(api_client, listings):
    response = api_client.get(reverse(URL_NAME))

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.django_db
def test_search_matches_the_pet_name(api_client, admin, listings):
    response = admin_get(api_client, admin, search="Rejected")

    assert pet_names(response) == {"Rejected Pet"}


@pytest.mark.django_db
def test_search_matches_the_business_name(api_client, admin, listings):
    response = admin_get(api_client, admin, search="Other Paws")

    assert pet_names(response) == {"Other Vendor Pet"}


@pytest.mark.django_db
def test_filter_by_review_status(api_client, admin, listings):
    approved = admin_get(api_client, admin, review_status="APPROVED")
    pending = admin_get(api_client, admin, review_status="pending")
    rejected = admin_get(api_client, admin, review_status="REJECTED")

    assert pet_names(approved) == {"Approved Pet", "Removed Pet", "Other Vendor Pet"}
    assert pet_names(pending) == {"Pending Pet"}
    assert pet_names(rejected) == {"Rejected Pet"}


@pytest.mark.django_db
def test_filter_deactivated_listings_only(api_client, admin, listings):
    response = admin_get(api_client, admin, is_active="false")

    assert pet_names(response) == {"Removed Pet"}


@pytest.mark.django_db
def test_filter_active_listings_only(api_client, admin, listings):
    response = admin_get(api_client, admin, is_active="true")

    assert pet_names(response) == ALL_NAMES - {"Removed Pet"}


@pytest.mark.django_db
def test_filter_by_listing_type(api_client, admin, listings):
    response = admin_get(api_client, admin, listing_type="sale")

    assert pet_names(response) == {"Other Vendor Pet"}


@pytest.mark.django_db
def test_filter_by_business(api_client, admin, listings, another_vendor_business):
    response = admin_get(api_client, admin, business=another_vendor_business.pk)

    assert pet_names(response) == {"Other Vendor Pet"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [
        {"review_status": "maybe"},
        {"is_active": "sometimes"},
        {"listing_type": "rent"},
        {"business": "abc"},
    ],
)
def test_bad_filter_values_are_rejected(api_client, admin, listings, params):
    response = admin_get(api_client, admin, **params)

    assert response.status_code == status.HTTP_400_BAD_REQUEST