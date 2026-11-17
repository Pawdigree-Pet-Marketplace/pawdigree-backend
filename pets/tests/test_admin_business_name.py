import pytest
from django.urls import reverse

from pets.tests.test_public_and_admin import make_pet


@pytest.fixture
def pet(vendor, vendor_business):
    return make_pet(vendor, vendor_business, "Buddy", approved=True)


@pytest.mark.django_db
def test_admin_list_shows_business_name(
    api_client, admin, pet, vendor_business
):
    api_client.force_authenticate(admin)

    response = api_client.get(reverse("pet-admin-list"))

    assert response.status_code == 200
    result = response.data["results"][0]
    assert result["business_name"] == vendor_business.name
    assert result["business"] == vendor_business.pk


@pytest.mark.django_db
def test_admin_detail_shows_business_name(
    api_client, admin, pet, vendor_business
):
    api_client.force_authenticate(admin)

    response = api_client.get(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk})
    )

    assert response.status_code == 200
    assert response.data["business_name"] == vendor_business.name


@pytest.mark.django_db
def test_admin_edit_response_shows_business_name(
    api_client, admin, pet, vendor_business
):
    api_client.force_authenticate(admin)

    response = api_client.patch(
        reverse("pet-admin-detail", kwargs={"pk": pet.pk}),
        {"name": "Fixed"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["business_name"] == vendor_business.name


@pytest.mark.django_db
def test_approve_response_shows_business_name(
    api_client, admin, vendor, vendor_business
):
    pending = make_pet(vendor, vendor_business, "Pending Pet")
    api_client.force_authenticate(admin)

    response = api_client.post(
        reverse("pet-admin-approve", kwargs={"pk": pending.pk})
    )

    assert response.status_code == 200
    assert response.data["business_name"] == vendor_business.name


@pytest.mark.django_db
def test_vendor_list_is_unchanged(api_client, vendor, pet):
    api_client.force_authenticate(vendor)

    response = api_client.get(reverse("pet-list"))

    assert response.status_code == 200
    data = response.data
    results = data["results"] if isinstance(data, dict) else data
    assert results
    assert "business_name" not in results[0]
