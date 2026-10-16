import pytest
from django.urls import reverse
from rest_framework import status

from businesses.models import Business
from pets.models import Pet


@pytest.fixture
def vendor_business(vendor):
    return Business.objects.create(
        vendor=vendor,
        name="Happy Paws",
        description="Pet care services",
        contact="+256700123456",
        email="happy-paws@example.com",
        address="Kampala Road",
        city_district="Kampala",
    )


@pytest.fixture
def another_vendor_business(another_vendor):
    return Business.objects.create(
        vendor=another_vendor,
        name="Other Paws",
        description="Pet care services",
        contact="+256700123457",
        email="other-paws@example.com",
        address="Entebbe Road",
        city_district="Entebbe",
    )


@pytest.fixture
def valid_pet_data(vendor_business):
    return {
        "business": str(vendor_business.pk),
        "listing_type": Pet.ListingType.ADOPTION,
        "name": "Buddy",
        "species": "Dog",
        "breed": "Mixed",
        "age": 12,
        "gender": Pet.Gender.MALE,
        "size": Pet.Size.MEDIUM,
        "description": "Friendly and playful.",
    }


@pytest.mark.django_db
def test_vendor_can_create_pet_listing(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert Pet.objects.filter(name="Buddy", vendor=vendor).exists()

    pet = Pet.objects.get(name="Buddy")
    assert pet.business.vendor_id == vendor.pk
    assert pet.approved is False


@pytest.mark.django_db
def test_vendor_cannot_create_listing_for_another_business(
    api_client,
    vendor,
    another_vendor_business,
    valid_pet_data,
):
    api_client.force_authenticate(user=vendor)
    valid_pet_data["business"] = str(another_vendor_business.pk)

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_customer_cannot_create_pet_listing(
    api_client, customer, valid_pet_data
):
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_unauthenticated_user_cannot_access_pet_listings(api_client):
    response = api_client.get(reverse("pet-list"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_vendor_only_sees_own_pet_listings(
    api_client,
    vendor,
    another_vendor,
    vendor_business,
    another_vendor_business,
):
    Pet.objects.create(
        vendor=vendor,
        business=vendor_business,
        name="My Pet",
        age=6,
        gender=Pet.Gender.FEMALE,
        size=Pet.Size.SMALL,
    )
    Pet.objects.create(
        vendor=another_vendor,
        business=another_vendor_business,
        name="Other Pet",
        age=8,
        gender=Pet.Gender.MALE,
        size=Pet.Size.MEDIUM,
    )

    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse("pet-list"))

    assert response.status_code == status.HTTP_200_OK

    results = (
        response.data["results"]
        if isinstance(response.data, dict)
        else response.data
    )
    names = {item["name"] for item in results}

    assert "My Pet" in names
    assert "Other Pet" not in names
