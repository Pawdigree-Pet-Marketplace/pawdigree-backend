import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
@pytest.mark.parametrize(
    "login_name", ["customer-login", "vendor-login", "admin-login"]
)
def test_repeated_failed_logins_are_throttled(login_name):
    client = APIClient()
    url = reverse(login_name)
    payload = {"email": "nobody@example.com", "password": "WrongPassword123"}

    for _ in range(10):
        response = client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    blocked = client.post(url, payload, format="json")

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
