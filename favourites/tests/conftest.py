import pytest

from accounts.models import User
from businesses.models import Business
from pets.models import Pet


@pytest.fixture
def second_customer(db):
    return User.objects.create_user(
        username="secondcustomer",
        email="second@example.com",
        password="TestPassword123!",
        role=User.Role.CUSTOMER,
    )


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
def make_pet(vendor, vendor_business):
    def _make_pet(name="Buddy", **extra):
        fields = {
            "approved": True,
            "age": 6,
            "gender": Pet.Gender.MALE,
            "size": Pet.Size.MEDIUM,
        }
        fields.update(extra)
        return Pet.objects.create(
            vendor=vendor, business=vendor_business, name=name, **fields
        )

    return _make_pet


@pytest.fixture
def pet(make_pet):
    return make_pet("Buddy")