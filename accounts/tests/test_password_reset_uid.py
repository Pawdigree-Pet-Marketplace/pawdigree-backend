import re

import pytest
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.models import User
from accounts.password_reset import PasswordResetTokenGeneratorService

CONFIRM_URL = "/api/auth/password-reset/confirm/"
REQUEST_URL = "/api/auth/password-reset/request/"
OLD_PASSWORD = "OldSecurePass123"
NEW_PASSWORD = "NewSecurePass456"


def make_user():
    return User.objects.create_user(
        username="resetuser",
        email="reset@example.com",
        password=OLD_PASSWORD,
    )


def encode_uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def make_token(user):
    return PasswordResetTokenGeneratorService().generate_token(user)


@pytest.mark.django_db
def test_reset_email_contains_encoded_uid(mailoutbox):
    user = make_user()

    response = APIClient().post(
        REQUEST_URL, {"email": user.email}, format="json"
    )

    assert 200 <= response.status_code < 300
    assert len(mailoutbox) == 1
    match = re.search(r"uid=([A-Za-z0-9_\-]+)", mailoutbox[0].body)
    assert match
    assert match.group(1) == encode_uid(user)


@pytest.mark.django_db
def test_confirm_with_uid_and_token_resets_password():
    user = make_user()

    response = APIClient().post(
        CONFIRM_URL,
        {
            "uid": encode_uid(user),
            "token": make_token(user),
            "new_password": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_bad_uid_and_bad_token_return_the_same_error():
    user = make_user()
    client = APIClient()

    bad_uid = client.post(
        CONFIRM_URL,
        {
            "uid": "not-a-valid-uid",
            "token": make_token(user),
            "new_password": NEW_PASSWORD,
        },
        format="json",
    )
    bad_token = client.post(
        CONFIRM_URL,
        {
            "uid": encode_uid(user),
            "token": "wrong-token",
            "new_password": NEW_PASSWORD,
        },
        format="json",
    )

    assert bad_uid.status_code == bad_token.status_code == 400
    assert bad_uid.data == bad_token.data
    user.refresh_from_db()
    assert user.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_confirm_with_email_still_works():
    user = make_user()

    response = APIClient().post(
        CONFIRM_URL,
        {
            "email": user.email,
            "token": make_token(user),
            "new_password": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_weak_new_password_is_rejected():
    user = make_user()

    response = APIClient().post(
        CONFIRM_URL,
        {
            "uid": encode_uid(user),
            "token": make_token(user),
            "new_password": "12345678",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "new_password" in response.data
    user.refresh_from_db()
    assert user.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_confirm_without_uid_or_email_is_rejected():
    user = make_user()

    response = APIClient().post(
        CONFIRM_URL,
        {"token": make_token(user), "new_password": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400
