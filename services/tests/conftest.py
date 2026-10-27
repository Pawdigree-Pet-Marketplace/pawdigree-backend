import pytest

from businesses.models import Business


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
def service_data(vendor_business):
    return {
        "business": vendor_business.pk,
        "name": "Dog Grooming",
        "service_type": "Grooming",
        "description": "Bathing and grooming for dogs.",
        "price": "50000.00",
        "duration": 60,
        "availability_status": "available",
    }
