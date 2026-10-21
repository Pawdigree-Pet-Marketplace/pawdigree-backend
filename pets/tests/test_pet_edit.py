import pytest
from django.urls import reverse
from rest_framework import status

from pets.models import Pet


def make_pet(vendor, business, **extra):
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
def test_vendor_can_edit_own_pet_and_it_goes_back_for_review(
    api_client, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business, approved=True)
    api_client.force_authenticate(user=vendor)

    response = api_client.patch(
        reverse("pet-update", kwargs={"pk": pet.pk}),
        {"name": "Buddy Jr"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK

    pet.refresh_from_db()

    assert pet.name == "Buddy Jr"
    assert pet.approved is False


@pytest.mark.django_db
def test_edit_rejects_image_ids_that_do_not_belong_to_the_listing(
    api_client, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business)
    api_client.force_authenticate(user=vendor)

    response = api_client.patch(
        reverse("pet-update", kwargs={"pk": pet.pk}),
        {"remove_image_ids": [999999]},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "remove_image_ids" in response.data


@pytest.mark.django_db
def test_vendor_cannot_edit_another_vendors_pet(
    api_client, vendor, another_vendor, another_vendor_business
):
    pet = make_pet(another_vendor, another_vendor_business)
    api_client.force_authenticate(user=vendor)

    response = api_client.patch(
        reverse("pet-update", kwargs={"pk": pet.pk}),
        {"name": "Hijacked"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND

    pet.refresh_from_db()

    assert pet.name == "Buddy"
