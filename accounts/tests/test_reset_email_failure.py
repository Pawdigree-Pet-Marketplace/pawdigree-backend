from unittest.mock import patch

import pytest
from django.urls import reverse

SEND = 'accounts.views.EmailMultiAlternatives.send'


@pytest.mark.django_db
def test_failed_send_looks_the_same_as_an_unknown_email(api_client, customer):
    url = reverse('password-reset-request')
    unknown = api_client.post(
        url, {'email': 'nobody@example.com'}, format='json'
    )

    with patch(SEND, side_effect=RuntimeError('mail provider down')):
        existing = api_client.post(
            url, {'email': customer.email}, format='json'
        )

    assert existing.status_code == 200
    assert existing.status_code == unknown.status_code
    assert existing.json() == unknown.json()


@pytest.mark.django_db
def test_failed_send_is_logged(api_client, customer, caplog):
    with patch(SEND, side_effect=RuntimeError('mail provider down')):
        api_client.post(
            reverse('password-reset-request'),
            {'email': customer.email},
            format='json',
        )

    assert 'could not be sent' in caplog.text
    assert customer.email not in caplog.text
