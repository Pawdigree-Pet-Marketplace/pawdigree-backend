import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User

pytestmark = pytest.mark.django_db


def check(username=None, client=None):
    params = {} if username is None else {"username": username}
    return (client or APIClient()).get(reverse("username-available"), params)


@pytest.fixture
def taken_user():
    return User.objects.create_user(
        username="taken_name",
        email="taken@example.com",
        password="Str0ng-pass-123!",
    )


def test_free_username_is_available():
    response = check("brand_new_name")

    assert response.status_code == 200
    assert response.json() == {"available": True}


def test_taken_username_is_not_available(taken_user):
    response = check("taken_name")

    assert response.status_code == 200
    assert response.json() == {"available": False}


def test_surrounding_spaces_are_ignored(taken_user):
    assert check("  taken_name  ").json() == {"available": False}


def test_missing_or_blank_username_is_a_400():
    assert check().status_code == 400
    assert check("   ").status_code == 400


def test_username_longer_than_allowed_is_not_available():
    assert check("x" * 151).json() == {"available": False}


def test_bad_token_does_not_turn_the_check_into_a_401():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    assert check("brand_new_name", client=client).status_code == 200
