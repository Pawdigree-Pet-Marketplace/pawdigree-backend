import pytest

RESET_URL = '/api/auth/password-reset/request/'
CONFIRM_URL = '/api/auth/password-reset/confirm/'
LOGIN_URL = '/api/auth/login/customer/'


@pytest.mark.django_db
def test_password_reset_request_is_throttled(api_client):
    # 5 requests per hour are allowed; the 6th is rejected.
    payload = {'email': 'nobody@example.com'}

    for _ in range(5):
        response = api_client.post(RESET_URL, payload, format='json')
        assert response.status_code == 200

    response = api_client.post(RESET_URL, payload, format='json')
    assert response.status_code == 429


@pytest.mark.django_db
def test_password_reset_confirm_is_throttled(api_client):
    # 10 attempts per hour are allowed; the 11th is rejected.
    payload = {
        'uid': 'invalid',
        'token': 'invalid',
        'new_password': 'SomeNewPassword123!',
    }

    for _ in range(10):
        response = api_client.post(CONFIRM_URL, payload, format='json')
        assert response.status_code == 400

    response = api_client.post(CONFIRM_URL, payload, format='json')
    assert response.status_code == 429


@pytest.mark.django_db
def test_reset_and_login_limits_are_separate(api_client):
    # Using up the reset allowance must not lock people out of logging in.
    for _ in range(6):
        api_client.post(
            RESET_URL, {'email': 'nobody@example.com'}, format='json'
        )

    response = api_client.post(
        LOGIN_URL,
        {'email': 'nobody@example.com', 'password': 'wrong'},
        format='json',
    )
    assert response.status_code == 400