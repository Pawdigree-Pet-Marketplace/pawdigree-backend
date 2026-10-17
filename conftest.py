import pytest
from rest_framework.test import APIClient

from accounts.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def vendor(db):
    return User.objects.create_user(
        username="testvendor",
        email="vendor@example.com",
        password="TestPassword123!",
        role=User.Role.VENDOR,
    )


@pytest.fixture
def another_vendor(db):
    return User.objects.create_user(
        username="anothervendor",
        email="another@example.com",
        password="TestPassword123!",
        role=User.Role.VENDOR,
    )


@pytest.fixture
def customer(db):
    return User.objects.create_user(
        username="testcustomer",
        email="customer@example.com",
        password="TestPassword123!",
        role=User.Role.CUSTOMER,
    )


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        username="testadmin",
        email="admin@example.com",
        password="TestPassword123!",
        role=User.Role.ADMIN,
    )


@pytest.fixture(autouse=True)
def disable_ssl_redirect(settings):
    # Production redirects HTTP to HTTPS; tests use plain HTTP.
    settings.SECURE_SSL_REDIRECT = False
