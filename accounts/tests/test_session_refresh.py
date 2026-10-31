import time

import pytest
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.token_utils import SESSION_CLAIM, SessionRefreshToken

DAY = 24 * 60 * 60


def session_token(user, days_old):
    token = SessionRefreshToken.for_user(user)
    token[SESSION_CLAIM] = token[SESSION_CLAIM] - days_old * DAY
    return token


@pytest.mark.django_db
def test_refresh_rejects_a_session_older_than_the_cap(api_client, customer):
    token = session_token(customer, days_old=31)

    response = api_client.post(
        reverse('token-refresh'), {'refresh': str(token)}, format='json'
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_accepts_a_session_inside_the_cap(api_client, customer):
    token = session_token(customer, days_old=29)

    response = api_client.post(
        reverse('token-refresh'), {'refresh': str(token)}, format='json'
    )

    assert response.status_code == 200
    assert 'access' in response.data
    assert 'refresh' in response.data


@pytest.mark.django_db
def test_rotation_keeps_the_original_login_time(api_client, customer):
    token = session_token(customer, days_old=10)
    original = token[SESSION_CLAIM]

    response = api_client.post(
        reverse('token-refresh'), {'refresh': str(token)}, format='json'
    )

    assert response.status_code == 200
    rotated = RefreshToken(response.data['refresh'])
    assert rotated[SESSION_CLAIM] == original


@pytest.mark.django_db
def test_token_from_before_the_cap_still_refreshes(api_client, customer):
    old_style = RefreshToken.for_user(customer)

    response = api_client.post(
        reverse('token-refresh'), {'refresh': str(old_style)}, format='json'
    )

    assert response.status_code == 200
    rotated = RefreshToken(response.data['refresh'])
    assert abs(rotated[SESSION_CLAIM] - time.time()) < 60
