from unittest.mock import patch

import pytest
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.serializers import GoogleLoginSerializer
from accounts.token_utils import revoke_user_tokens

PASSWORD = "SecurePass123"
GOOGLE_INFO = {"email": "owner@example.com", "email_verified": True}


def google_login():
    with patch(
        "accounts.serializers.verify_google_token", return_value=GOOGLE_INFO
    ):
        serializer = GoogleLoginSerializer(data={"credential": "token"})
        assert serializer.is_valid(), serializer.errors
    return serializer.validated_data


@pytest.mark.django_db
def test_revoke_user_tokens_blacklists_existing_refresh_tokens():
    user = User.objects.create_user(
        username="someone", email="someone@example.com", password=PASSWORD
    )
    old_token = str(RefreshToken.for_user(user))

    revoke_user_tokens(user)

    with pytest.raises(TokenError):
        RefreshToken(old_token)


@pytest.mark.django_db
def test_google_login_revokes_old_sessions_when_it_wipes_a_password():
    user = User.objects.create_user(
        username="owner",
        email="owner@example.com",
        password=PASSWORD,
        role=User.Role.CUSTOMER,
    )
    old_token = str(RefreshToken.for_user(user))

    data = google_login()

    with pytest.raises(TokenError):
        RefreshToken(old_token)
    RefreshToken(data["refresh"])  # the new session still works
    user.refresh_from_db()
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_google_login_keeps_sessions_of_accounts_without_a_password():
    user = User.objects.create_user(
        username="owner",
        email="owner@example.com",
        password=None,
        role=User.Role.CUSTOMER,
    )
    old_token = str(RefreshToken.for_user(user))

    google_login()

    RefreshToken(old_token)  # not revoked, so no error
