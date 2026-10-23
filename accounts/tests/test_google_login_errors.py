import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User

GENERIC = "Could not sign in. Please try again."


def sign_in_with_google(monkeypatch, email):
    monkeypatch.setattr(
        "accounts.serializers.verify_google_token",
        lambda credential: {"email": email, "given_name": "G", "family_name": "User"},
    )
    return APIClient().post(
        reverse("google-login"), {"credential": "fake-token"}, format="json"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("role", [User.Role.VENDOR, User.Role.ADMIN, User.Role.SYSTEM_ADMIN])
def test_google_login_does_not_reveal_non_customer_accounts(monkeypatch, role):
    User.objects.create_user(
        username="other", email="other@example.com", password="SecurePass123", role=role
    )

    response = sign_in_with_google(monkeypatch, "other@example.com")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "access" not in response.data
    assert GENERIC in str(response.data)

    text = str(response.data).lower()
    for word in ("customer", "vendor", "admin"):
        assert word not in text


@pytest.mark.django_db
def test_google_login_does_not_reveal_inactive_accounts(monkeypatch):
    user = User.objects.create_user(
        username="inactive", email="inactive@example.com",
        password="SecurePass123", role=User.Role.CUSTOMER,
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = sign_in_with_google(monkeypatch, "inactive@example.com")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "inactive" not in str(response.data).lower()


@pytest.mark.django_db
def test_new_google_user_becomes_a_customer(monkeypatch):
    response = sign_in_with_google(monkeypatch, "brandnew@example.com")

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert User.objects.get(email="brandnew@example.com").role == User.Role.CUSTOMER
