import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from businesses.models import Business
from pets.models import Pet, PetImage


@pytest.mark.django_db
def test_valid_pet_image_is_accepted(make_image):
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

    pet_image = PetImage(pet=pet, image=make_image())

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


@pytest.mark.django_db
def test_vendor_can_create_pet_listing_with_multiple_images(
    api_client, vendor, valid_pet_data, make_image
):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("pet-list"),
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
def test_invalid_image_does_not_create_pet_listing(
    api_client, vendor, valid_pet_data
):
    api_client.force_authenticate(user=vendor)

    invalid_image = SimpleUploadedFile(
        "not-an-image.txt",
        b"This is not a valid image",
        content_type="text/plain",
    )

    response = api_client.post(
        reverse("pet-list"),
        {
            **valid_pet_data,
            "images": [invalid_image],
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Pet.objects.filter(vendor=vendor).count() == 0


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


@pytest.mark.django_db
def test_system_admin_cannot_create_pet_listing(
    api_client,
    system_admin,
    valid_pet_data,
):
    api_client.force_authenticate(user=system_admin)

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_system_admin_cannot_access_pet_listings(
    api_client,
    system_admin,
    vendor,
    vendor_business,
):
    Pet.objects.create(
        vendor=vendor,
        business=vendor_business,
        name="Vendor Pet",
        age=6,
        gender=Pet.Gender.FEMALE,
        size=Pet.Size.SMALL,
    )

    api_client.force_authenticate(user=system_admin)

    response = api_client.get(reverse("pet-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"verification_status": Business.VerificationStatus.PENDING},
        {"verification_status": Business.VerificationStatus.DRAFT},
        {"verification_status": Business.VerificationStatus.SUSPENDED},
        {"is_active": False},
        {"business_type": Business.BusinessType.PRODUCT_SELLER},
        {"business_type": None},
    ],
)
def test_vendor_cannot_create_listing_for_unverified_business(
    api_client, vendor, vendor_business, valid_pet_data, overrides
):
    for field, value in overrides.items():
        setattr(vendor_business, field, value)
    vendor_business.save()
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("pet-list"),
        valid_pet_data,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "business" in response.data
    assert not Pet.objects.filter(name="Buddy").exists()
