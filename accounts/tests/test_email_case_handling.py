from types import SimpleNamespace

import pytest

from accounts.models import User
from accounts.serializers import (
    AdminLoginSerializer,
    AdminRegistrationSerializer,
    CustomerLoginSerializer,
    CustomerRegistrationSerializer,
    VendorLoginSerializer,
    VendorRegistrationSerializer,
)

PASSWORD = "SecurePass123"

REGISTRATION = [
    CustomerRegistrationSerializer,
    VendorRegistrationSerializer,
    AdminRegistrationSerializer,
]

LOGIN = [
    (User.Role.CUSTOMER, CustomerLoginSerializer),
    (User.Role.VENDOR, VendorLoginSerializer),
    (User.Role.ADMIN, AdminLoginSerializer),
]


def registration_data(email, username="newuser"):
    return {
        "username": username,
        "first_name": "New",
        "last_name": "User",
        "email": email,
        "phone": "+256700123456",
        "password": PASSWORD,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("serializer_class", REGISTRATION)
def test_registration_rejects_email_differing_only_by_case(serializer_class):
    User.objects.create_user(
        username="existing",
        email="taken@example.com",
        password=PASSWORD,
    )

    serializer = serializer_class(
        data=registration_data("Taken@Example.com")
    )

    assert not serializer.is_valid()
    assert "email" in serializer.errors


@pytest.mark.django_db
@pytest.mark.parametrize("serializer_class", REGISTRATION)
def test_registration_stores_email_lowercased(serializer_class, system_admin):
    # The admin serializer records who created the account, so it needs the
    # request's user in its context. The other two ignore the context.
    serializer = serializer_class(
        data=registration_data("New@Example.COM"),
        context={"request": SimpleNamespace(user=system_admin)},
    )

    assert serializer.is_valid(), serializer.errors
    user = serializer.save()

    assert user.email == "new@example.com"


@pytest.mark.django_db
@pytest.mark.parametrize("role, serializer_class", LOGIN)
def test_login_works_with_different_email_capitalization(
    role, serializer_class
):
    User.objects.create_user(
        username="mixedcase",
        email="Anna@Example.com",
        password=PASSWORD,
        role=role,
    )

    serializer = serializer_class(
        data={"email": "anna@example.com", "password": PASSWORD}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["user"].email == "Anna@example.com"
