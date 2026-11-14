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
        business_type=Business.BusinessType.PET_SALE_ADOPTION,
        verification_status=Business.VerificationStatus.APPROVED,
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
        business_type=Business.BusinessType.PET_SALE_ADOPTION,
        verification_status=Business.VerificationStatus.APPROVED,
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