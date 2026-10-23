import re

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User

PASSWORD = "SecurePass123"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def make_user(role, verified=False, username="loginuser"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
        role=role,
        is_email_verified=verified,
    )


def login(name, user, password=PASSWORD):
    return APIClient().post(
        reverse(name),
        {"email": user.email, "password": password},
        format="json",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role, login_name",
    [
        (User.Role.CUSTOMER, "customer-login"),
        (User.Role.VENDOR, "vendor-login"),
    ],
)
def test_unverified_login_asks_for_a_code_and_gives_no_tokens(
    role, login_name, mailoutbox
):
    user = make_user(role)

    response = login(login_name, user)

    assert response.status_code == 200
    assert response.data["verification_required"] is True
    assert response.data["verification_token"]
    assert response.data["email"] == "l***@example.com"
    assert "access" not in response.data
    assert "refresh" not in response.data
    assert len(mailoutbox) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role, login_name",
    [
        (User.Role.CUSTOMER, "customer-login"),
        (User.Role.VENDOR, "vendor-login"),
    ],
)
def test_verified_login_returns_tokens_and_sends_no_email(
    role, login_name, mailoutbox
):
    user = make_user(role, verified=True)

    response = login(login_name, user)

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert "verification_required" not in response.data
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_admin_login_does_not_need_a_code(mailoutbox):
    user = make_user(User.Role.ADMIN)

    response = login("admin-login", user)

    assert response.status_code == 200
    assert "access" in response.data
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_wrong_password_looks_the_same_for_unverified_accounts():
    user = make_user(User.Role.CUSTOMER)

    wrong_password = login("customer-login", user, "WrongPassword123")
    unknown = APIClient().post(
        reverse("customer-login"),
        {"email": "nobody@example.com", "password": PASSWORD},
        format="json",
    )

    assert wrong_password.status_code == 400
    assert wrong_password.data == unknown.data


@pytest.mark.django_db
def test_second_login_within_cooldown_does_not_send_another_email(mailoutbox):
    user = make_user(User.Role.CUSTOMER)

    first = login("customer-login", user)
    second = login("customer-login", user)

    assert first.data["verification_required"] is True
    assert second.data["verification_required"] is True
    assert second.data["resend_available_in"] > 0
    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_full_flow_login_then_code_then_tokens(mailoutbox):
    user = make_user(User.Role.CUSTOMER)

    first = login("customer-login", user)
    code = re.search(r"\b(\d{6})\b", mailoutbox[0].body).group(1)
    verified = APIClient().post(
        reverse("verify-email"),
        {
            "verification_token": first.data["verification_token"],
            "code": code,
        },
        format="json",
    )

    assert verified.status_code == 200
    assert "access" in verified.data
    assert "refresh" in verified.data
    assert "user" not in verified.data
    again = login("customer-login", user)
    assert "access" in again.data
    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_google_login_marks_the_user_verified(monkeypatch, mailoutbox):
    monkeypatch.setattr(
        "accounts.serializers.verify_google_token",
        lambda token: {
            "email": "gnew@example.com",
            "email_verified": True,
            "given_name": "G",
            "family_name": "User",
        },
    )

    response = APIClient().post(
        reverse("google-login"), {"credential": "fake-token"}, format="json"
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert User.objects.get(email="gnew@example.com").is_email_verified is True
    assert len(mailoutbox) == 0
