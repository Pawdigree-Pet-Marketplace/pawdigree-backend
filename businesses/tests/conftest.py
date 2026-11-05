import pytest

from businesses.models import Business

DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@pytest.fixture
def business(vendor):
    return Business.objects.create(
        vendor=vendor,
        name="Happy Paws",
        description="Pet care services",
        contact="+256700123456",
        email="business@example.com",
        address="Kampala Road",
        city_district="Kampala",
    )


@pytest.fixture
def business_hours():
    """Return valid opening hours for all seven days."""
    return {
        day: {
            "is_open": True,
            "open": "09:00",
            "close": "17:00",
        }
        for day in DAYS
    }


@pytest.fixture
def valid_business_data(business_hours):
    """Return valid business information."""
    return {
        "name": "New Happy Paws",
        "description": "Pet care services",
        "contact": "+256700123456",
        "email": "newbusiness@example.com",
        "address": "Kampala Road",
        "city_district": "Kampala",
        "business_type": "PRODUCT_SELLER",
        "business_hours": business_hours,
    }