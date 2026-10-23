import pytest

from accounts.models import User
from accounts.serializers import CustomerProfileSerializer

PASSWORD = "SecurePass123"


@pytest.mark.django_db
def test_profile_email_differing_only_by_case_is_rejected():
    User.objects.create_user(
        username="existing",
        email="taken@example.com",
        password=PASSWORD,
        role=User.Role.CUSTOMER,
    )
    me = User.objects.create_user(
        username="me",
        email="me@example.com",
        password=PASSWORD,
        role=User.Role.CUSTOMER,
    )

    serializer = CustomerProfileSerializer(
        instance=me, data={"email": "Taken@Example.com"}, partial=True
    )

    assert not serializer.is_valid()
    assert "email" in serializer.errors


@pytest.mark.django_db
def test_profile_keeps_own_email_even_if_case_changes():
    me = User.objects.create_user(
        username="me",
        email="me@example.com",
        password=PASSWORD,
        role=User.Role.CUSTOMER,
    )

    serializer = CustomerProfileSerializer(
        instance=me, data={"email": "ME@example.com"}, partial=True
    )

    assert serializer.is_valid(), serializer.errors
