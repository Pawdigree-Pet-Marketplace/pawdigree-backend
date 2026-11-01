from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.permissions import IsAdmin
from common.permissions import (
    IsSystemAdmin as AccountIsSystemAdmin,
)
from common.permissions import (
    IsSystemAdminRoleOnly,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def system_admin(db):
    return User.objects.create_superuser(
        username="system_admin_test",
        email="systemadmin_test@example.com",
        password="SystemPass123!",
    )


@pytest.fixture
def regular_admin(db):
    return User.objects.create_user(
        username="regular_admin_test",
        email="admin_test@example.com",
        password="AdminPass123!",
        role=User.Role.ADMIN,
        is_staff=True,
    )


@pytest.fixture
def role_system_admin(db):
    # A system admin identified by role, not by is_superuser.
    return User.objects.create_user(
        username="role_system_admin_test",
        email="rolesystemadmin_test@example.com",
        password="SystemPass123!",
        role=User.Role.SYSTEM_ADMIN,
    )


@pytest.mark.django_db
def test_system_admin_can_create_admin_account(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        {
            "username": "new_admin_test",
            "first_name": "New",
            "last_name": "Administrator",
            "email": "newadmin_test@example.com",
            "phone": "0700000000",
            "password": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED

    created_admin = User.objects.get(email="newadmin_test@example.com")

    assert created_admin.role == User.Role.ADMIN
    assert created_admin.is_staff is True
    assert created_admin.is_superuser is False
    assert created_admin.check_password("StrongPass123!")


@pytest.mark.django_db
def test_regular_admin_cannot_create_admin_account(
    api_client, regular_admin
):
    api_client.force_authenticate(user=regular_admin)

    response = api_client.post(
        reverse("admin-register"),
        {
            "username": "blocked_admin_test",
            "first_name": "Blocked",
            "last_name": "Administrator",
            "email": "blockedadmin_test@example.com",
            "phone": "0700000001",
            "password": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not User.objects.filter(
        email="blockedadmin_test@example.com"
    ).exists()


@pytest.mark.django_db
def test_unauthenticated_user_cannot_create_admin_account(api_client):
    response = api_client.post(
        reverse("admin-register"),
        {
            "username": "unauthorized_admin_test",
            "first_name": "Unauthorized",
            "last_name": "Administrator",
            "email": "unauthorized_admin_test@example.com",
            "phone": "0700000002",
            "password": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert not User.objects.filter(
        email="unauthorized_admin_test@example.com"
    ).exists()


@pytest.mark.django_db
def test_user_with_system_admin_role_can_create_admin_account(
    api_client, role_system_admin
):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        {
            "username": "role_created_admin_test",
            "first_name": "Role",
            "last_name": "Created",
            "email": "rolecreated_test@example.com",
            "phone": "0700000003",
            "password": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.get(
        email="rolecreated_test@example.com"
    ).role == User.Role.ADMIN


@pytest.mark.django_db
def test_customer_cannot_create_admin_account(api_client):
    customer = User.objects.create_user(
        username="customer_cannot_create_admin",
        email="customer_cannot_create_admin@example.com",
        password="StrongPass123!",
        role=User.Role.CUSTOMER,
    )
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse("admin-register"),
        {
            "username": "customer_admin_attempt",
            "first_name": "Customer",
            "last_name": "Blocked",
            "email": "customer_blocked_admin@example.com",
            "phone": "0700000004",
            "password": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not User.objects.filter(
        email="customer_blocked_admin@example.com"
    ).exists()


@pytest.mark.django_db
def test_vendor_cannot_create_admin_account(api_client):
    vendor = User.objects.create_user(
        username="vendor_cannot_create_admin",
        email="vendor_cannot_create_admin@example.com",
        password="StrongPass123!",
        role=User.Role.VENDOR,
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("admin-register"),
        {
            "username": "vendor_admin_attempt",
            "first_name": "Vendor",
            "last_name": "Blocked",
            "email": "vendor_blocked_admin@example.com",
            "phone": "0700000005",
            "password": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not User.objects.filter(
        email="vendor_blocked_admin@example.com"
    ).exists()


@pytest.mark.django_db
def test_admin_permission_allows_admin_and_system_admin(
    regular_admin, system_admin, role_system_admin
):
    permission = IsAdmin()

    for user in (regular_admin, system_admin, role_system_admin):
        request = SimpleNamespace(user=user)
        assert permission.has_permission(request, None) is True


@pytest.mark.django_db
def test_account_system_admin_permission_allows_superuser_and_system_admin_role(
    system_admin, role_system_admin
):
    permission = AccountIsSystemAdmin()

    for user in (system_admin, role_system_admin):
        request = SimpleNamespace(user=user)
        assert permission.has_permission(request, None) is True


@pytest.mark.django_db
def test_account_system_admin_permission_rejects_anonymous_and_non_system_admin(
    regular_admin,
):
    permission = AccountIsSystemAdmin()

    request = SimpleNamespace(user=None)
    assert permission.has_permission(request, None) is False

    request = SimpleNamespace(user=regular_admin)
    assert permission.has_permission(request, None) is False


@pytest.mark.django_db
def test_role_only_system_admin_permission_requires_role_only(
    role_system_admin, system_admin, regular_admin
):
    permission = IsSystemAdminRoleOnly()

    request = SimpleNamespace(user=role_system_admin)
    assert permission.has_permission(request, None) is True

    for user in (system_admin, regular_admin):
        request = SimpleNamespace(user=user)
        assert permission.has_permission(request, None) is False



def admin_payload(**overrides):
    payload = {
        "username": "created_admin",
        "first_name": "Created",
        "last_name": "Admin",
        "email": "created_admin@example.com",
        "phone": "0700000006",
        "password": "StrongPass123!",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_superuser_without_system_admin_role_cannot_create_admin_account(
    api_client,
):
    superuser = User.objects.create_superuser(
        username="plain_superuser",
        email="plain_superuser@example.com",
        password="SuperPass123!",
    )
    api_client.force_authenticate(user=superuser)

    response = api_client.post(
        reverse("admin-register"), admin_payload(), format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not User.objects.filter(email="created_admin@example.com").exists()


@pytest.mark.django_db
def test_submitted_role_is_ignored(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        admin_payload(role="SYSTEM_ADMIN"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    created = User.objects.get(email="created_admin@example.com")
    assert created.role == User.Role.ADMIN
    assert response.data["role"] == User.Role.ADMIN
    assert User.objects.filter(role=User.Role.SYSTEM_ADMIN).count() == 1


@pytest.mark.django_db
def test_duplicate_email_is_rejected_ignoring_case(
    api_client, role_system_admin, regular_admin
):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        admin_payload(email=regular_admin.email.upper()),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert User.objects.filter(email__iexact=regular_admin.email).count() == 1


@pytest.mark.django_db
def test_password_is_hashed_and_never_returned(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"), admin_payload(), format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert "password" not in response.data
    created = User.objects.get(email="created_admin@example.com")
    assert created.password != "StrongPass123!"
    assert created.check_password("StrongPass123!")


@pytest.mark.django_db
def test_weak_password_is_rejected(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        admin_payload(password="123"),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not User.objects.filter(email="created_admin@example.com").exists()


@pytest.mark.django_db
def test_created_admin_is_active_and_can_log_in(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)
    api_client.post(reverse("admin-register"), admin_payload(), format="json")
    api_client.force_authenticate(user=None)

    created = User.objects.get(email="created_admin@example.com")
    assert created.is_active is True
    assert created.is_staff is True
    assert created.is_superuser is False

    response = api_client.post(
        reverse("admin-login"),
        {"email": "created_admin@example.com", "password": "StrongPass123!"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["role"] == User.Role.ADMIN



@pytest.mark.django_db
def test_username_is_optional_and_generated_from_email(
    api_client, role_system_admin
):
    api_client.force_authenticate(user=role_system_admin)
    payload = admin_payload(email="no.username@example.com")
    del payload["username"]

    response = api_client.post(
        reverse("admin-register"), payload, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    created = User.objects.get(email="no.username@example.com")
    assert created.username == "no.username"


@pytest.mark.django_db
def test_supplied_username_is_kept(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        admin_payload(username="chosen_name"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.get(
        email="created_admin@example.com"
    ).username == "chosen_name"


@pytest.mark.django_db
def test_privilege_fields_in_request_are_ignored(api_client, role_system_admin):
    api_client.force_authenticate(user=role_system_admin)

    response = api_client.post(
        reverse("admin-register"),
        admin_payload(is_superuser=True, is_active=False, role="SYSTEM_ADMIN"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    created = User.objects.get(email="created_admin@example.com")
    assert created.role == User.Role.ADMIN
    assert created.is_superuser is False
    assert created.is_active is True
