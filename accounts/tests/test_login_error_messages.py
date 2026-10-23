import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User

PASSWORD = "SecurePass123"

WRONG_PORTAL = [
    (User.Role.VENDOR, "customer-login"),
    (User.Role.ADMIN, "customer-login"),
    (User.Role.SYSTEM_ADMIN, "customer-login"),
    (User.Role.CUSTOMER, "vendor-login"),
    (User.Role.ADMIN, "vendor-login"),
    (User.Role.CUSTOMER, "admin-login"),
    (User.Role.VENDOR, "admin-login"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("account_role, login_name", WRONG_PORTAL)
def test_wrong_portal_login_looks_like_any_other_failed_login(
    account_role, login_name
):
    user = User.objects.create_user(
        username="portaluser",
        email="portal@example.com",
        password=PASSWORD,
        role=account_role,
    )
    client = APIClient()
    url = reverse(login_name)

    wrong_portal = client.post(
        url, {"email": user.email, "password": PASSWORD}, format="json"
    )
    wrong_password = client.post(
        url, {"email": user.email, "password": "WrongPassword123"}, format="json"
    )
    unknown_email = client.post(
        url, {"email": "nobody@example.com", "password": PASSWORD}, format="json"
    )

    assert wrong_portal.status_code == status.HTTP_400_BAD_REQUEST
    assert wrong_portal.data == wrong_password.data == unknown_email.data

    text = str(wrong_portal.data).lower()
    for word in ("customer", "vendor", "admin"):
        assert word not in text
