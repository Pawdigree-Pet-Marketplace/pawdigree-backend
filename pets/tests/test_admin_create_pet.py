import pytest
from rest_framework import status

from pets.models import Pet

URL = "/api/pets/admin/"


@pytest.mark.django_db
def test_admin_can_create_an_approved_pet_for_a_vendor_business(
    api_client, admin, vendor, valid_pet_data
):
    api_client.force_authenticate(admin)

    response = api_client.post(URL, valid_pet_data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    pet = Pet.objects.get(pk=response.data["pet_id"])
    assert pet.vendor == vendor
    assert pet.approved is True
    assert pet.reviewed_at is not None
    assert response.data["business_name"] == pet.business.name


@pytest.mark.django_db
def test_vendor_cannot_use_the_admin_create_endpoint(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(vendor)

    response = api_client.post(URL, valid_pet_data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_cannot_create_a_pet_for_an_inactive_business(
    api_client, admin, vendor_business, valid_pet_data
):
    vendor_business.is_active = False
    vendor_business.save()
    api_client.force_authenticate(admin)

    response = api_client.post(URL, valid_pet_data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "business" in response.data
