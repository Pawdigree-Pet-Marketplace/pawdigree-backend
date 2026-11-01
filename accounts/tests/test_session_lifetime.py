import time

import pytest
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.token_utils import SESSION_CLAIM, SessionRefreshToken

DAY = 24 * 60 * 60


def token_started_days_ago(user, days):
    token = SessionRefreshToken.for_user(user)
    token[SESSION_CLAIM] = token[SESSION_CLAIM] - days * DAY
    return str(token)


@pytest.mark.django_db
def test_new_token_is_stamped_with_the_login_time(customer):
    token = SessionRefreshToken.for_user(customer)

    assert abs(token[SESSION_CLAIM] - time.time()) < 60


@pytest.mark.django_db
def test_session_older_than_the_cap_is_rejected(customer):
    with pytest.raises(TokenError):
        SessionRefreshToken(token_started_days_ago(customer, 31))


@pytest.mark.django_db
def test_session_inside_the_cap_is_accepted(customer):
    token = SessionRefreshToken(token_started_days_ago(customer, 29))

    assert SESSION_CLAIM in token.payload


@pytest.mark.django_db
def test_token_from_before_the_cap_is_accepted_and_stamped(customer):
    old_style = RefreshToken.for_user(customer)

    token = SessionRefreshToken(str(old_style))

    assert abs(token[SESSION_CLAIM] - time.time()) < 60