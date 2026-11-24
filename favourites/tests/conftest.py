import pytest
import itertools

from accounts.models import User
from businesses.models import Business
from pets.models import Pet
from businesses.models import Business
from categories.models import Category
from products.models import Product

_n = itertools.count(1)


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


@pytest.fixture
def make_product(vendor):
    def factory(name="Rope toy", **extra):
        n = next(_n)
        data = dict(
            business=Business.objects.create(
                vendor=vendor,
                name=f"Shop {n}",
                description="A shop",
                contact="+256700000000",
                email=f"shop{n}@example.com",
                address="1 Main Street",
                city_district="Kampala",
                business_type=Business.BusinessType.PRODUCT_SELLER,
                verification_status=Business.VerificationStatus.APPROVED,
                is_active=True,
            ),
            category=Category.objects.create(
                name=f"Merch {n}", kind=Category.Kind.MERCHANDISE, is_active=True
            ),
            name=name,
            price="10.00",
            stock_quantity=5,
            approved=True,
            is_active=True,
        )
        data.update(extra)
        return Product.objects.create(**data)

    return factory


@pytest.fixture
def product(make_product):
    return make_product()