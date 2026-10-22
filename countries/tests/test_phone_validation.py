import pytest
from rest_framework import serializers

from accounts.serializers import CustomerRegistrationSerializer
from common.phone import normalize_phone_number


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+256700123456", "+256700123456"),
        ("0700123456", "+256700123456"),
        ("+256 700-123-456", "+256700123456"),
        ("+254712345678", "+254712345678"),
        ("+447911123456", "+447911123456"),
    ],
)
def test_valid_numbers_are_normalized(raw, expected):
    assert normalize_phone_number(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["abc", "+256", "12345", "+2567001", ""],
)
def test_invalid_numbers_are_rejected(raw):
    with pytest.raises(serializers.ValidationError):
        normalize_phone_number(raw)


def _registration_data(phone):
    return {
        "username": "phoneuser",
        "first_name": "Phone",
        "last_name": "User",
        "email": "phoneuser@example.com",
        "phone": phone,
        "password": "StrongPass123!",
    }


@pytest.mark.django_db
def test_registration_normalizes_phone():
    serializer = CustomerRegistrationSerializer(
        data=_registration_data("0700123456")
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["phone"] == "+256700123456"


@pytest.mark.django_db
def test_registration_rejects_invalid_phone():
    serializer = CustomerRegistrationSerializer(
        data=_registration_data("not-a-number")
    )
    assert not serializer.is_valid()
    assert "phone" in serializer.errors