import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from accounts.models import User
from businesses.models import Business
from pets.models import Pet, PetImage


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
