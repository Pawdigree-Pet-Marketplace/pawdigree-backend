from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.serializers import GoogleTokenError

pytestmark = pytest.mark.django_db

PATCH_TARGET = "accounts.serializers.verify_google_token"
GOOGLE_INFO = {
    "email": "New.Vendor@Example.com",
    "given_name": "Ada",
    "family_name": "Lovelace",
}


def sign_in(info=None, url_name="google-vendor-login"):
    with patch(PATCH_TARGET, return_value=info or GOOGLE_INFO):
        return APIClient().post(
            reverse(url_name), {"credential": "fake-token"}, format="json"
        )


def test_new_google_user_becomes_a_verified_vendor_with_tokens():
    response = sign_in()

    assert response.status_code == 200
    assert set(response.json()) == {"access", "refresh"}
    user = User.objects.get(email="new.vendor@example.com")
    assert user.role == User.Role.VENDOR
    assert user.is_email_verified is True
    assert user.first_name == "Ada"
    assert user.phone == ""
    assert not user.has_usable_password()


def test_existing_customer_with_same_email_stays_a_separate_account():
    User.objects.create_user(
        username="ada_customer",
        email="new.vendor@example.com",
        password="Str0ng-pass-123!",
        role=User.Role.CUSTOMER,
    )

    response = sign_in()

    assert response.status_code == 200
    assert User.objects.filter(email="new.vendor@example.com").count() == 2
    customer = User.objects.get(
        email="new.vendor@example.com", role=User.Role.CUSTOMER
    )
    assert customer.has_usable_password()


def test_second_sign_in_reuses_the_same_vendor():
    sign_in()
    sign_in()

    assert User.objects.filter(
        email="new.vendor@example.com", role=User.Role.VENDOR
    ).count() == 1


def test_unverified_vendor_loses_the_old_password_when_google_verifies_it():
    user = User.objects.create_user(
        username="ada_vendor",
        email="new.vendor@example.com",
        password="Str0ng-pass-123!",
        role=User.Role.VENDOR,
    )
    User.objects.filter(pk=user.pk).update(is_email_verified=False)

    response = sign_in()

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_email_verified is True
    assert not user.has_usable_password()


def test_inactive_vendor_cannot_sign_in():
    user = User.objects.create_user(
        username="ada_vendor",
        email="new.vendor@example.com",
        password="Str0ng-pass-123!",
        role=User.Role.VENDOR,
    )
    User.objects.filter(pk=user.pk).update(is_active=False)

    response = sign_in()

    assert response.status_code == 400
    assert "access" not in response.json()


def test_bad_google_token_is_a_400():
    with patch(PATCH_TARGET, side_effect=GoogleTokenError("Bad token.")):
        response = APIClient().post(
            reverse("google-vendor-login"),
            {"credential": "bad"},
            format="json",
        )

    assert response.status_code == 400
    assert User.objects.count() == 0


def test_customer_google_login_still_creates_customers():
    response = sign_in(url_name="google-login")

    assert response.status_code == 200
    user = User.objects.get(email="new.vendor@example.com")
    assert user.role == User.Role.CUSTOMER
