import pytest
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.password_reset import PasswordResetTokenGeneratorService

CONFIRM_URL = "/api/auth/password-reset/confirm/"


@pytest.mark.django_db
def test_password_reset_revokes_existing_refresh_tokens():
    user = User.objects.create_user(
        username="resetuser",
        email="reset@example.com",
        password="OldSecurePass123",
        role=User.Role.CUSTOMER,
    )
    old_token = str(RefreshToken.for_user(user))

    response = APIClient().post(
        CONFIRM_URL,
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": PasswordResetTokenGeneratorService().generate_token(user),
            "new_password": "NewSecurePass456",
        },
        format="json",
    )

    assert response.status_code == 200
    with pytest.raises(TokenError):
        RefreshToken(old_token)
