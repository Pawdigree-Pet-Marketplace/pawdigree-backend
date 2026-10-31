import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User

PASSWORD = "StrongPass123!"


def payload(**overrides):
    data = {
        "first_name": "Ada",
        "last_name": "Nakato",
        "email": "ada@example.com",
        "phone": "+256700123456",
        "password": PASSWORD,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["customer-register", "vendor-register"])
def test_username_is_optional(url_name):
    response = APIClient().post(reverse(url_name), payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.get(email="ada@example.com").username == "ada"


@pytest.mark.django_db
def test_generated_username_avoids_clashes():
    User.objects.create_user(
        username="ada", email="other@example.com", password=PASSWORD
    )

    response = APIClient().post(
        reverse("customer-register"), payload(), format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.get(email="ada@example.com").username == "ada2"


@pytest.mark.django_db
def test_supplied_username_is_still_used():
    response = APIClient().post(
        reverse("customer-register"),
        payload(username="adan"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.get(email="ada@example.com").username == "adan"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "phone",
    [
        "+256700123456",
        "0700123456",
        "700123456",
        "256700123456",
        "+2560700123456",
    ],
)
def test_phone_formats_are_stored_as_e164(phone):
    response = APIClient().post(
        reverse("customer-register"), payload(phone=phone), format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.get(email="ada@example.com").phone == "+256700123456"