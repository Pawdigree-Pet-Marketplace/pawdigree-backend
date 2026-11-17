import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from audit.models import AuditLog
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


@pytest.mark.django_db
def test_admin_create_is_recorded_in_the_audit_log(
    api_client, admin, vendor_business, valid_pet_data
):
    api_client.force_authenticate(admin)

    response = api_client.post(URL, valid_pet_data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    entry = AuditLog.objects.get(action="pet.admin_created")
    assert entry.actor == admin
    assert entry.details == {"business": str(vendor_business.pk)}


@pytest.mark.django_db
def test_admin_can_create_a_pet_with_multiple_images(
    api_client, admin, vendor, valid_pet_data, make_image
):
    api_client.force_authenticate(admin)

    response = api_client.post(
        URL,
        {
            **valid_pet_data,
            "images": [
                make_image("buddy-1.png"),
                make_image("buddy-2.png"),
            ],
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED

    pet = Pet.objects.get(name="Buddy")
    images = list(pet.images.all())

    assert pet.vendor == vendor
    assert len(images) == 2
    assert images[0].is_primary is True
    assert images[0].position == 0
    assert images[1].is_primary is False
    assert images[1].position == 1


@pytest.mark.django_db
def test_invalid_image_does_not_create_an_admin_pet_listing(
    api_client, admin, valid_pet_data
):
    api_client.force_authenticate(admin)

    invalid_image = SimpleUploadedFile(
        "not-an-image.txt",
        b"This is not a valid image",
        content_type="text/plain",
    )

    response = api_client.post(
        URL,
        {**valid_pet_data, "images": [invalid_image]},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Pet.objects.count() == 0
