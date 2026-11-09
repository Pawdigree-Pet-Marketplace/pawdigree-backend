from decimal import Decimal

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product


def make_user(name, role):
    return User.objects.create_user(
        username=name, email=f"{name}@example.com",
        password="Test12345!", role=role,
    )
    
def make_business(vendor, name="Paws Place", approved=True, active=True):
    status = (
        Business.VerificationStatus.APPROVED if approved
        else Business.VerificationStatus.PENDING
    )
    return Business.objects.create(
        vendor=vendor, name=name, description="Pet supplies",
        contact="0700000000", email="shop@example.com",
        address="1 Main St", city_district="Kampala",
        verification_status=status, is_active=active,
    )
    
    
def make_category(name="Toys", active=True):
    return Category.objects.create(name=name, is_active=active)


def make_product(business, category, name="Chew toy", price="10.00",
                 stock=5, active=True):
    return Product.objects.create(
        business=business, category=category, name=name,
        price=Decimal(price), stock_quantity=stock, is_active=active,
    )


def money(value):
    """Read a money value from JSON, whether it came as text or a number."""
    return Decimal(str(value))    