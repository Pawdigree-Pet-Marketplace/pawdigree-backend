import pytest
from django.urls import reverse
from rest_framework import status

from pets.models import Pet
from pets.tests.test_public_and_admin import make_pet, pet_names


def url(pet):
    return reverse("pet-admin-detail", kwargs={"pk": pet.pk})


@pytest.fixture
def pet(vendor, vendor_business):
    return make_pet(vendor, vendor_business, "Buddy", approved=True)


def admin_patch(api_client, user, pet, data):
    api_client.force_authenticate(user)
    return api_client.patch(url(pet), data, format="json")


@pytest.mark.django_db
def test_admin_can_correct_any_vendors_listing(api_client, admin, pet):
    response = admin_patch(
        api_client, admin, pet,
        {"name": "Corrected Name", "description": "Removed misleading claims."},
    )

    assert response.status_code == status.HTTP_200_OK
    pet.refresh_from_db()
    assert pet.name == "Corrected Name"
    assert pet.description == "Removed misleading claims."


@pytest.mark.django_db
def test_system_admin_can_correct_a_listing(api_client, system_admin, pet):
    response = admin_patch(api_client, system_admin, pet, {"name": "Fixed"})

    assert response.status_code == status.HTTP_200_OK
    pet.refresh_from_db()
    assert pet.name == "Fixed"


@pytest.mark.django_db
def test_edit_keeps_an_approved_listing_approved(api_client, admin, pet):
    admin_patch(api_client, admin, pet, {"name": "Fixed"})

    pet.refresh_from_db()
    assert pet.approved is True


@pytest.mark.django_db
def test_edit_keeps_a_pending_listing_pending(
    api_client, admin, vendor, vendor_business
):
    pending = make_pet(vendor, vendor_business, "Pending Pet")

    admin_patch(api_client, admin, pending, {"name": "Fixed"})

    pending.refresh_from_db()
    assert pending.review_status == "PENDING"


@pytest.mark.django_db
def test_edit_keeps_a_rejected_listing_rejected(
    api_client, admin, vendor, vendor_business
):
    rejected = make_pet(
        vendor, vendor_business, "Rejected Pet", rejection_reason="Blurry photos"
    )

    admin_patch(api_client, admin, rejected, {"name": "Fixed"})

    rejected.refresh_from_db()
    assert rejected.review_status == "REJECTED"
    assert rejected.rejection_reason == "Blurry photos"


@pytest.mark.django_db
def test_admin_can_edit_a_deactivated_listing(
    api_client, admin, vendor, vendor_business
):
    removed = make_pet(
        vendor, vendor_business, "Removed Pet", approved=True, is_active=False
    )

    response = admin_patch(api_client, admin, removed, {"name": "Fixed"})

    assert response.status_code == status.HTTP_200_OK
    removed.refresh_from_db()
    assert removed.name == "Fixed"
    assert removed.is_active is False


@pytest.mark.django_db
def test_edit_cannot_move_a_listing_to_another_business_or_owner(
    api_client, admin, pet, vendor, vendor_business,
    another_vendor, another_vendor_business,
):
    response = admin_patch(
        api_client, admin, pet,
        {
            "name": "Fixed",
            "business": str(another_vendor_business.pk),
            "vendor": another_vendor.pk,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    pet.refresh_from_db()
    assert pet.business_id == vendor_business.pk
    assert pet.vendor_id == vendor.pk


@pytest.mark.django_db
def test_edit_cannot_change_review_or_active_state(api_client, admin, pet):
    response = admin_patch(
        api_client, admin, pet,
        {
            "name": "Fixed",
            "approved": False,
            "rejection_reason": "Changed my mind",
            "is_active": False,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    pet.refresh_from_db()
    assert pet.approved is True
    assert pet.rejection_reason == ""
    assert pet.is_active is True


@pytest.mark.django_db
def test_sale_listing_needs_a_price(api_client, admin, pet):
    response = admin_patch(api_client, admin, pet, {"listing_type": "SALE"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "price" in response.data


@pytest.mark.django_db
def test_adoption_listing_cannot_have_a_price(api_client, admin, pet):
    response = admin_patch(api_client, admin, pet, {"price": "100000"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "price" in response.data


@pytest.mark.django_db
def test_admin_can_turn_an_adoption_into_a_sale_with_a_price(
    api_client, admin, pet
):
    response = admin_patch(
        api_client, admin, pet, {"listing_type": "SALE", "price": "250000"}
    )

    assert response.status_code == status.HTTP_200_OK
    pet.refresh_from_db()
    assert pet.listing_type == Pet.ListingType.SALE
    assert str(pet.price) == "250000.00"


@pytest.mark.django_db
def test_invalid_values_are_rejected(api_client, admin, pet):
    response = admin_patch(api_client, admin, pet, {"gender": "ROBOT"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "gender" in response.data


@pytest.mark.django_db
def test_put_replaces_the_listing_details(api_client, admin, pet):
    api_client.force_authenticate(admin)

    response = api_client.put(
        url(pet),
        {
            "name": "Replaced",
            "species": "Cat",
            "age": 24,
            "gender": "MALE",
            "size": "LARGE",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    pet.refresh_from_db()
    assert (pet.name, pet.species, pet.age, pet.size) == (
        "Replaced", "Cat", 24, "LARGE",
    )


@pytest.mark.django_db
def test_admin_can_view_one_listing_even_when_deactivated(
    api_client, admin, vendor, vendor_business
):
    removed = make_pet(
        vendor, vendor_business, "Removed Pet", approved=True, is_active=False
    )
    api_client.force_authenticate(admin)

    response = api_client.get(url(removed))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Removed Pet"
    assert response.data["is_active"] is False


@pytest.mark.django_db
def test_unknown_listing_returns_404(api_client, admin):
    api_client.force_authenticate(admin)

    response = api_client.patch(
        reverse("pet-admin-detail", kwargs={"pk": 999999}),
        {"name": "Nope"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_vendor_cannot_use_the_admin_edit_even_on_their_own_listing(
    api_client, vendor, pet
):
    response = admin_patch(api_client, vendor, pet, {"name": "Sneaky"})

    assert response.status_code == status.HTTP_403_FORBIDDEN
    pet.refresh_from_db()
    assert pet.name == "Buddy"


@pytest.mark.django_db
def test_customer_cannot_edit_a_listing(api_client, customer, pet):
    response = admin_patch(api_client, customer, pet, {"name": "Sneaky"})

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_anonymous_cannot_edit_a_listing(api_client, pet):
    response = api_client.patch(url(pet), {"name": "Sneaky"}, format="json")

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.django_db
def test_removing_hides_a_listing_from_customers_but_not_from_admins(
    api_client, admin, pet
):
    api_client.force_authenticate(admin)

    response = api_client.delete(url(pet))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert "Buddy" not in pet_names(api_client.get(reverse("pet-public-list")))
    assert "Buddy" in pet_names(api_client.get(reverse("pet-admin-list")))


@pytest.mark.django_db
def test_removing_twice_returns_404(api_client, admin, pet):
    api_client.force_authenticate(admin)
    api_client.delete(url(pet))

    response = api_client.delete(url(pet))

    assert response.status_code == status.HTTP_404_NOT_FOUND
