import io
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status

from accounts.models import User
from businesses.models import Business
from pets.models import Pet, PetImage


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


def make_image_file(filename="pet.png", *, size=(10, 10), color=(0, 255, 0)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return SimpleUploadedFile(
        filename,
        buffer.getvalue(),
        content_type="image/png",
    )


@pytest.mark.django_db
def test_valid_pet_image_is_accepted():
    vendor = User.objects.create_user(
        username="petvendor",
        email="petvendor@example.com",
        password="TestPassword123!",
        role=User.Role.VENDOR,
    )
    business = Business.objects.create(
        vendor=vendor,
        name="Pet Business",
        description="Pet products",
        contact="+256700123456",
        email="petbusiness@example.com",
        address="Kampala Road",
        city_district="Kampala",
    )
    pet = Pet.objects.create(
        vendor=vendor,
        business=business,
        name="Luna",
        species="Dog",
        breed="Labrador",
        age=12,
        gender=Pet.Gender.FEMALE,
        size=Pet.Size.MEDIUM,
        description="Friendly dog",
        listing_type=Pet.ListingType.ADOPTION,
    )

    pet_image = PetImage(pet=pet, image=make_image_file())

    pet_image.full_clean()
    pet_image.save()
    assert pet.images.exists()


@pytest.mark.django_db
def test_invalid_pet_image_is_rejected():
    vendor = User.objects.create_user(
        username="petvendor2",
        email="petvendor2@example.com",
        password="TestPassword123!",
        role=User.Role.VENDOR,
    )
    business = Business.objects.create(
        vendor=vendor,
        name="Pet Business 2",
        description="Pet products",
        contact="+256700123456",
        email="petbusiness2@example.com",
        address="Kampala Road",
        city_district="Kampala",
    )
    pet = Pet.objects.create(
        vendor=vendor,
        business=business,
        name="Max",
        species="Cat",
        breed="Mixed",
        age=8,
        gender=Pet.Gender.MALE,
        size=Pet.Size.SMALL,
        description="Calm cat",
        listing_type=Pet.ListingType.ADOPTION,
    )

    pet_image = PetImage(
        pet=pet,
        image=SimpleUploadedFile(
            "pet.txt",
            b"not-a-real-image",
            content_type="text/plain",
        ),
    )

    with pytest.raises(ValidationError):
        pet_image.full_clean()


@pytest.mark.django_db
def test_vendor_can_create_pet_listing(api_client, vendor, valid_pet_data):
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
def test_customer_cannot_create_pet_listing(api_client, customer, valid_pet_data):
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


def make_test_image(name="pet.png"):
    image = Image.new("RGB", (20, 20), color="green")
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")

    return SimpleUploadedFile(
        name,
        image_bytes.getvalue(),
        content_type="image/png",
    )


@pytest.mark.django_db
def test_vendor_can_create_pet_listing_with_multiple_images(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("pet-list"),
        {
            **valid_pet_data,
            "images": [
                make_test_image("buddy-1.png"),
                make_test_image("buddy-2.png"),
            ],
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED

    pet = Pet.objects.get(name="Buddy", vendor=vendor)
    images = list(pet.images.all())

    assert len(images) == 2
    assert images[0].is_primary is True
    assert images[0].position == 0
    assert images[1].is_primary is False
    assert images[1].position == 1
    assert all(
        image.image.storage.exists(image.image.name)
        for image in images
    )


@pytest.mark.django_db
def test_pet_listing_requires_mandatory_fields(api_client, vendor, valid_pet_data):
    api_client.force_authenticate(user=vendor)
    valid_pet_data.pop("name")

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "name" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_pet_listing_rejects_negative_age(api_client, vendor, valid_pet_data):
    api_client.force_authenticate(user=vendor)
    valid_pet_data["age"] = -1

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "age" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_sale_listing_requires_positive_price(api_client, vendor, valid_pet_data):
    api_client.force_authenticate(user=vendor)
    valid_pet_data["listing_type"] = Pet.ListingType.SALE
    valid_pet_data["price"] = "0.00"

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "price" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_adoption_listing_rejects_price(api_client, vendor, valid_pet_data):
    api_client.force_authenticate(user=vendor)
    valid_pet_data["price"] = "100.00"

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "price" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_sale_listing_accepts_positive_price(api_client, vendor, valid_pet_data):
    api_client.force_authenticate(user=vendor)
    valid_pet_data["listing_type"] = Pet.ListingType.SALE
    valid_pet_data["price"] = "250000.00"

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert Pet.objects.filter(
        vendor=vendor,
        name="Buddy",
        price="250000.00",
    ).exists()
