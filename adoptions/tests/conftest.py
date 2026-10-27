import pytest

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
def pet(vendor, vendor_business):
    return Pet.objects.create(
        vendor=vendor,
        business=vendor_business,
        name="Buddy",
        age=6,
        gender=Pet.Gender.MALE,
        size=Pet.Size.MEDIUM,
        approved=True,
    )


@pytest.fixture
def application_data(pet):
    return {
        "pet": pet.pk,
        "home_type": "APARTMENT",
        "has_outdoor_space": True,
        "has_other_pets": False,
        "previous_pet_experience": "NONE",
        "message": "I work from home and have always wanted a dog.",
    }