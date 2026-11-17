import pytest
from django.urls import reverse

from pets.tests.test_public_and_admin import make_pet


def words(count):
    return " ".join(["word"] * count)


@pytest.mark.django_db
def test_vendor_can_create_a_listing_with_300_words(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(vendor)
    data = {**valid_pet_data, "description": words(300)}

    response = api_client.post(reverse("pet-list"), data, format="json")

    assert response.status_code == 201


@pytest.mark.django_db
def test_vendor_cannot_create_a_listing_with_301_words(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(vendor)
    data = {**valid_pet_data, "description": words(301)}

    response = api_client.post(reverse("pet-list"), data, format="json")

    assert response.status_code == 400
    assert "description" in response.data


@pytest.mark.django_db
def test_admin_edit_with_a_long_description_is_rejected(
    api_client, admin, vendor, vendor_business
):
    pet = make_pet(vendor, vendor_business, "Buddy", approved=True)
    before = pet.description
    api_client.force_authenticate(admin)

    response = api_client.patch(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk}),
        {"description": words(301)},
        format="json",
    )

    assert response.status_code == 400
    pet.refresh_from_db()
    assert pet.description == before
    assert pet.approved is True
