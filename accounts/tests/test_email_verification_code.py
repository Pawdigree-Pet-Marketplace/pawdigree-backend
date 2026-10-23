import re
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import EmailVerificationCode, User
from accounts.verification import (
    MAX_ATTEMPTS,
    issue_code,
    make_verification_token,
)


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def make_user():
    return User.objects.create_user(
        username="verifyme",
        email="verifyme@example.com",
        password="SecurePass123",
        role=User.Role.CUSTOMER,
    )


def post_verify(user, code):
    return APIClient().post(
        reverse("verify-email"),
        {"verification_token": make_verification_token(user), "code": code},
        format="json",
    )


def post_resend(user):
    return APIClient().post(
        reverse("verify-email-resend"),
        {"verification_token": make_verification_token(user)},
        format="json",
    )


@pytest.mark.django_db
def test_code_is_six_digits_and_only_a_hash_is_stored():
    user = make_user()

    code = issue_code(user)

    record = EmailVerificationCode.objects.get(user=user)
    assert re.fullmatch(r"\d{6}", code)
    assert record.code_hash != code
    assert len(record.code_hash) == 64


@pytest.mark.django_db
def test_new_code_replaces_the_previous_one():
    user = make_user()
    first = issue_code(user)
    second = issue_code(user)
    while second == first:
        second = issue_code(user)

    assert EmailVerificationCode.objects.filter(user=user).count() == 1
    assert post_verify(user, first).status_code == 400
    assert post_verify(user, second).status_code == 200


@pytest.mark.django_db
def test_correct_code_verifies_email_and_returns_tokens():
    user = make_user()
    code = issue_code(user)

    response = post_verify(user, code)

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    user.refresh_from_db()
    assert user.is_email_verified is True
    assert not EmailVerificationCode.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_a_code_can_only_be_used_once():
    user = make_user()
    code = issue_code(user)

    assert post_verify(user, code).status_code == 200
    assert post_verify(user, code).status_code == 400


@pytest.mark.django_db
def test_wrong_code_is_rejected_and_does_not_verify():
    user = make_user()
    issue_code(user)

    response = post_verify(user, "000000")

    assert response.status_code == 400
    assert "code" in response.data
    user.refresh_from_db()
    assert user.is_email_verified is False


@pytest.mark.django_db
def test_code_stops_working_after_too_many_attempts():
    user = make_user()
    code = issue_code(user)
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(MAX_ATTEMPTS):
        assert post_verify(user, wrong).status_code == 400

    assert post_verify(user, code).status_code == 400
    user.refresh_from_db()
    assert user.is_email_verified is False


@pytest.mark.django_db
def test_expired_code_is_rejected():
    user = make_user()
    code = issue_code(user)
    EmailVerificationCode.objects.filter(user=user).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert post_verify(user, code).status_code == 400
    user.refresh_from_db()
    assert user.is_email_verified is False


@pytest.mark.django_db
def test_invalid_verification_token_is_rejected():
    response = APIClient().post(
        reverse("verify-email"),
        {"verification_token": "not-a-real-token", "code": "123456"},
        format="json",
    )

    assert response.status_code == 400
    assert "verification_token" in response.data


@pytest.mark.django_db
def test_resend_sends_a_new_code_by_email(mailoutbox):
    user = make_user()
    old_code = issue_code(user)
    EmailVerificationCode.objects.filter(user=user).update(
        last_sent_at=timezone.now() - timedelta(minutes=2)
    )

    response = post_resend(user)

    assert response.status_code == 200
    assert len(mailoutbox) == 1
    match = re.search(r"\b(\d{6})\b", mailoutbox[0].body)
    assert match
    new_code = match.group(1)
    if new_code != old_code:
        assert post_verify(user, old_code).status_code == 400
    assert post_verify(user, new_code).status_code == 200


@pytest.mark.django_db
def test_resend_has_a_cooldown(mailoutbox):
    user = make_user()
    issue_code(user)

    response = post_resend(user)

    assert response.status_code == 429
    assert response.data["retry_after"] > 0
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_resend_for_verified_user_sends_nothing(mailoutbox):
    user = make_user()
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])

    response = post_resend(user)

    assert response.status_code == 200
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_verify_endpoint_is_rate_limited():
    client = APIClient()
    url = reverse("verify-email")
    payload = {"verification_token": "bad", "code": "123456"}

    for _ in range(10):
        assert client.post(url, payload, format="json").status_code == 400

    assert client.post(url, payload, format="json").status_code == 429
