import pytest

from accounts.serializers import (
    CustomerRegistrationSerializer,
    VendorRegistrationSerializer,
)

SERIALIZERS = [CustomerRegistrationSerializer, VendorRegistrationSerializer]


def registration_data(password):
    return {
        "username": "newuser",
        "first_name": "New",
        "last_name": "User",
        "email": "new@example.com",
        "phone": "+256700123456",
        "password": password,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("serializer_class", SERIALIZERS)
@pytest.mark.parametrize("weak_password", ["12345678", "password"])
def test_weak_passwords_are_rejected(serializer_class, weak_password):
    serializer = serializer_class(data=registration_data(weak_password))

    assert not serializer.is_valid()
    assert "password" in serializer.errors


@pytest.mark.django_db
@pytest.mark.parametrize("serializer_class", SERIALIZERS)
def test_strong_password_is_accepted(serializer_class):
    serializer = serializer_class(data=registration_data("SecurePass123"))

    assert serializer.is_valid(), serializer.errors
