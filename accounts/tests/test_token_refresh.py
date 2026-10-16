import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


@pytest.fixture
def refresh_user():
    user = User.objects.create_user(
        username='refreshuser',
        email='refreshuser@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
    )
    return user, RefreshToken.for_user(user)


@pytest.mark.django_db
def test_valid_refresh_token_returns_new_tokens(refresh_user):
    _, refresh_token = refresh_user
    client = APIClient()

    response = client.post(
        reverse('token-refresh'),
        {'refresh': str(refresh_token)},
        format='json',
    )

    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'refresh' in response.data


@pytest.mark.django_db
def test_rotated_refresh_token_cannot_be_reused(refresh_user):
    _, refresh_token = refresh_user
    client = APIClient()
    old_token = str(refresh_token)

    client.post(reverse('token-refresh'), {'refresh': old_token}, format='json')

    response = client.post(
        reverse('token-refresh'),
        {'refresh': old_token},
        format='json',
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_invalid_refresh_token_is_rejected():
    client = APIClient()

    response = client.post(
        reverse('token-refresh'),
        {'refresh': 'not-a-real-token'},
        format='json',
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_missing_refresh_token_is_rejected():
    client = APIClient()

    response = client.post(reverse('token-refresh'), {}, format='json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_logged_out_refresh_token_cannot_refresh(refresh_user):
    user, refresh_token = refresh_user
    client = APIClient()
    token = str(refresh_token)

    client.force_authenticate(user=user)
    logout_response = client.post(
        reverse('logout'),
        {'refresh': token},
        format='json',
    )
    assert logout_response.status_code == status.HTTP_200_OK

    client.force_authenticate(user=None)
    response = client.post(
        reverse('token-refresh'),
        {'refresh': token},
        format='json',
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_deactivated_user_cannot_refresh(refresh_user):
    user, refresh_token = refresh_user
    user.is_active = False
    user.save(update_fields=['is_active'])
    client = APIClient()

    response = client.post(
        reverse('token-refresh'),
        {'refresh': str(refresh_token)},
        format='json',
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED