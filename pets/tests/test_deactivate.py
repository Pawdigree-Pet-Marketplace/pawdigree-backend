import pytest
from django.urls import reverse
from rest_framework import status

from pets.models import Pet


def create_test_pet(vendor, business, **extra):
    return Pet.objects.create(
        vendor=vendor,
        business=business,
        name="Buddy",
        age=6,
        gender=Pet.Gender.MALE,
        size=Pet.Size.SMALL,
        **extra,
    )


@pytest.mark.django_db
def test_vendor_can_deactivate_own_pet_listing(
    api_client, vendor, vendor_business
):
    pet = create_test_pet(vendor, vendor_business)
    api_client.force_authenticate(user=vendor)

    response = api_client.delete(reverse("pet-detail", kwargs={"pk": pet.pk}))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    pet.refresh_from_db()
    assert pet.is_active is False
    assert Pet.objects.filter(pk=pet.pk).exists()


@pytest.mark.django_db
def test_vendor_cannot_deactivate_another_vendors_pet(
    api_client, vendor, vendor_business, another_vendor
):
    pet = create_test_pet(vendor, vendor_business)
    api_client.force_authenticate(user=another_vendor)

    response = api_client.delete(reverse("pet-detail", kwargs={"pk": pet.pk}))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    pet.refresh_from_db()
    assert pet.is_active is True


@pytest.mark.django_db
def test_deactivating_an_already_deactivated_pet_returns_404(
    api_client, vendor, vendor_business
):
    pet = create_test_pet(vendor, vendor_business, is_active=False)
    api_client.force_authenticate(user=vendor)

    response = api_client.delete(reverse("pet-detail", kwargs={"pk": pet.pk}))

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_customer_cannot_deactivate_pet_listing(
    api_client, customer, vendor, vendor_business
):
    pet = create_test_pet(vendor, vendor_business)
    api_client.force_authenticate(user=customer)

    response = api_client.delete(reverse("pet-detail", kwargs={"pk": pet.pk}))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    pet.refresh_from_db()
    assert pet.is_active is True


@pytest.mark.django_db
def test_unauthenticated_user_cannot_deactivate_pet_listing(
    api_client, vendor, vendor_business
):
    pet = create_test_pet(vendor, vendor_business)

    response = api_client.delete(reverse("pet-detail", kwargs={"pk": pet.pk}))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    pet.refresh_from_db()
    assert pet.is_active is True


@pytest.mark.django_db
def test_system_admin_cannot_use_vendor_deactivate_endpoint(
    api_client, system_admin, vendor, vendor_business
):
    pet = create_test_pet(vendor, vendor_business)
    api_client.force_authenticate(user=system_admin)

    response = api_client.delete(reverse("pet-detail", kwargs={"pk": pet.pk}))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    pet.refresh_from_db()
    assert pet.is_active is True


@pytest.mark.django_db
def test_publicly_visible_excludes_deactivated_and_unapproved_pets(
    vendor, vendor_business
):
    visible = create_test_pet(vendor, vendor_business, approved=True)
    create_test_pet(vendor, vendor_business, approved=True, is_active=False)
    create_test_pet(vendor, vendor_business, approved=False)

    assert list(Pet.objects.publicly_visible()) == [visible]


@pytest.mark.django_db
def test_vendor_cannot_set_is_active_when_creating_listing(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("pet-list"),
        {**valid_pet_data, "is_active": False},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert Pet.objects.get(pk=response.data["pet_id"]).is_active is True