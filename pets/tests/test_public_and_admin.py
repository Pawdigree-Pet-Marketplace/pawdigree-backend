import pytest
from django.urls import reverse
from rest_framework import status

from pets.models import Pet


def make_pet(vendor, business, name, **extra):
    return Pet.objects.create(
        vendor=vendor,
        business=business,
        name=name,
        age=6,
        gender=Pet.Gender.FEMALE,
        size=Pet.Size.SMALL,
        **extra,
    )


def get_results(response):
    if isinstance(response.data, dict):
        return response.data["results"]

    return response.data


def pet_names(response):
    return {item["name"] for item in get_results(response)}


@pytest.mark.django_db
def test_anyone_can_browse_approved_active_pets(
    api_client, vendor, vendor_business
):
    make_pet(vendor, vendor_business, "Visible Pet", approved=True)
    make_pet(
        vendor, vendor_business, "Deactivated Pet",
        approved=True, is_active=False,
    )
    make_pet(vendor, vendor_business, "Unapproved Pet", approved=False)

    response = api_client.get(reverse("pet-public-list"))

    assert response.status_code == status.HTTP_200_OK
    assert pet_names(response) == {"Visible Pet"}


@pytest.mark.django_db
def test_public_list_hides_vendor_and_internal_fields(
    api_client, vendor, vendor_business
):
    make_pet(vendor, vendor_business, "Visible Pet", approved=True)

    response = api_client.get(reverse("pet-public-list"))
    item = get_results(response)[0]

    for field in ("vendor", "approved", "is_active"):
        assert field not in item


@pytest.mark.django_db
def test_pet_leaves_public_list_after_vendor_deactivates_it(
    api_client, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business, "Soon Gone", approved=True)

    assert "Soon Gone" in pet_names(api_client.get(reverse("pet-public-list")))

    api_client.force_authenticate(user=vendor)
    delete_response = api_client.delete(
        reverse("pet-detail", kwargs={"pk": pet.pk})
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    api_client.force_authenticate(user=None)

    assert "Soon Gone" not in pet_names(
        api_client.get(reverse("pet-public-list"))
    )


@pytest.mark.django_db
def test_public_list_ignores_an_invalid_token(
    api_client, vendor, vendor_business
):
    make_pet(vendor, vendor_business, "Visible Pet", approved=True)
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    response = api_client.get(reverse("pet-public-list"))

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_vendor_list_still_shows_deactivated_pets_as_inactive(
    api_client, vendor, vendor_business
):
    make_pet(vendor, vendor_business, "Inactive Pet", is_active=False)
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse("pet-list"))
    item = next(
        item for item in get_results(response)
        if item["name"] == "Inactive Pet"
    )

    assert response.status_code == status.HTTP_200_OK
    assert item["is_active"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["admin", "system_admin"])
def test_admin_roles_can_deactivate_any_listing(
    api_client, request, role_fixture, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business, "Any Vendor Pet", approved=True)
    api_client.force_authenticate(user=request.getfixturevalue(role_fixture))

    response = api_client.delete(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk})
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT

    pet.refresh_from_db()

    assert pet.is_active is False
    assert Pet.objects.filter(pk=pet.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["vendor", "customer"])
def test_non_admins_cannot_use_admin_deactivate_route(
    api_client, request, role_fixture, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business, "Protected Pet", approved=True)
    api_client.force_authenticate(user=request.getfixturevalue(role_fixture))

    response = api_client.delete(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk})
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

    pet.refresh_from_db()

    assert pet.is_active is True


@pytest.mark.django_db
def test_unauthenticated_user_cannot_use_admin_deactivate_route(
    api_client, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business, "Protected Pet", approved=True)

    response = api_client.delete(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk})
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    pet.refresh_from_db()

    assert pet.is_active is True


@pytest.mark.django_db
def test_admin_deactivating_an_already_deactivated_pet_returns_404(
    api_client, admin, vendor, vendor_business
):
    pet = make_pet(
        vendor, vendor_business, "Already Inactive",
        approved=True, is_active=False,
    )
    api_client.force_authenticate(user=admin)

    response = api_client.delete(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk})
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_public_list_only_shows_available_pets(
    api_client, vendor, vendor_business
):
    make_pet(
        vendor,
        vendor_business,
        "Available Pet",
        approved=True,
        adoption_status=Pet.AdoptionStatus.AVAILABLE,
    )
    make_pet(
        vendor,
        vendor_business,
        "Pending Pet",
        approved=True,
        adoption_status=Pet.AdoptionStatus.PENDING,
    )
    make_pet(
        vendor,
        vendor_business,
        "Adopted Pet",
        approved=True,
        adoption_status=Pet.AdoptionStatus.ADOPTED,
    )

    response = api_client.get(reverse("pet-public-list"))

    assert response.status_code == status.HTTP_200_OK
    assert pet_names(response) == {"Available Pet"}
