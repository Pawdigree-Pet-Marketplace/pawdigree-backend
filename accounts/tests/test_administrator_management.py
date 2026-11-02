import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.services import set_administrator_active

User = get_user_model()

PASSWORD = "StrongPass123!"


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
        role=role,
        **extra,
    )


def admin_login(email):
    return APIClient().post(
        reverse("admin-login"),
        {"email": email, "password": PASSWORD},
        format="json",
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sysadmin(db):
    return make_user("sysadmin", User.Role.SYSTEM_ADMIN)


@pytest.fixture
def admin_user(db):
    return make_user("managed_admin", User.Role.ADMIN, is_staff=True)


@pytest.fixture
def customer(db):
    return make_user("a_customer", User.Role.CUSTOMER)


@pytest.fixture
def vendor(db):
    return make_user("a_vendor", User.Role.VENDOR)


def detail_url(user):
    return reverse("administrator-detail", args=[user.pk])


# ---- permissions -----------------------------------------------------------

@pytest.mark.django_db
def test_only_system_admin_role_can_use_management_endpoints(
    api_client, sysadmin, admin_user, customer, vendor
):
    urls = [
        ("get", reverse("administrator-list")),
        ("get", detail_url(admin_user)),
        ("patch", detail_url(admin_user)),
        ("post", reverse("administrator-deactivate", args=[admin_user.pk])),
        ("post", reverse("administrator-activate", args=[admin_user.pk])),
    ]

    for user in (admin_user, customer, vendor):
        api_client.force_authenticate(user=user)
        for method, url in urls:
            response = getattr(api_client, method)(url, {}, format="json")
            assert response.status_code == status.HTTP_403_FORBIDDEN, (
                user.role, method, url
            )

    api_client.force_authenticate(user=None)
    response = api_client.get(reverse("administrator-list"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_superuser_without_system_admin_role_is_blocked(api_client):
    superuser = User.objects.create_superuser(
        username="plain_superuser",
        email="plain_superuser@example.com",
        password=PASSWORD,
    )
    api_client.force_authenticate(user=superuser)

    response = api_client.get(reverse("administrator-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ---- list and retrieve -----------------------------------------------------

@pytest.mark.django_db
def test_list_returns_only_administrators(
    api_client, sysadmin, admin_user, customer
):
    other_admin = make_user("second_admin", User.Role.ADMIN, is_staff=True)
    api_client.force_authenticate(user=sysadmin)

    response = api_client.get(reverse("administrator-list"))

    assert response.status_code == status.HTTP_200_OK
    ids = {item["id"] for item in response.data["results"]}
    assert ids == {admin_user.id, other_admin.id}
    assert "password" not in response.data["results"][0]


@pytest.mark.django_db
def test_retrieve_returns_safe_fields(api_client, sysadmin, admin_user):
    api_client.force_authenticate(user=sysadmin)

    response = api_client.get(detail_url(admin_user))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == admin_user.email
    assert response.data["role"] == User.Role.ADMIN
    assert "password" not in response.data


@pytest.mark.django_db
def test_other_account_ids_return_404(
    api_client, sysadmin, customer, vendor
):
    api_client.force_authenticate(user=sysadmin)

    for target in (sysadmin, customer, vendor):
        assert api_client.get(detail_url(target)).status_code == 404
        assert api_client.patch(
            detail_url(target), {"first_name": "X"}, format="json"
        ).status_code == 404
        assert api_client.post(
            reverse("administrator-deactivate", args=[target.pk])
        ).status_code == 404

    sysadmin.refresh_from_db()
    assert sysadmin.is_active is True


# ---- create at the management URL -----------------------------------------

@pytest.mark.django_db
def test_system_admin_can_create_admin_at_management_url(
    api_client, sysadmin
):
    api_client.force_authenticate(user=sysadmin)

    response = api_client.post(
        reverse("administrator-list"),
        {
            "username": "via_management",
            "first_name": "Via",
            "last_name": "Management",
            "email": "via_management@example.com",
            "phone": "0700000011",
            "password": PASSWORD,
            "role": "SYSTEM_ADMIN",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    created = User.objects.get(email="via_management@example.com")
    assert created.role == User.Role.ADMIN


# ---- update ----------------------------------------------------------------

@pytest.mark.django_db
def test_patch_changes_only_permitted_fields(
    api_client, sysadmin, admin_user
):
    api_client.force_authenticate(user=sysadmin)

    response = api_client.patch(
        detail_url(admin_user),
        {
            "first_name": "Renamed",
            "last_name": "Person",
            "phone": "0700000010",
            "role": "SYSTEM_ADMIN",
            "email": "hijack@example.com",
            "is_active": False,
            "is_staff": False,
            "is_superuser": True,
            "username": "hijacked",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    admin_user.refresh_from_db()
    assert admin_user.first_name == "Renamed"
    assert admin_user.last_name == "Person"
    assert admin_user.phone.startswith("+")
    assert admin_user.role == User.Role.ADMIN
    assert admin_user.email == "managed_admin@example.com"
    assert admin_user.username == "managed_admin"
    assert admin_user.is_active is True
    assert admin_user.is_staff is True
    assert admin_user.is_superuser is False


@pytest.mark.django_db
def test_put_is_not_allowed(api_client, sysadmin, admin_user):
    api_client.force_authenticate(user=sysadmin)

    response = api_client.put(
        detail_url(admin_user), {"first_name": "X"}, format="json"
    )

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ---- activate and deactivate -----------------------------------------------

@pytest.mark.django_db
def test_deactivated_admin_loses_all_access(
    api_client, sysadmin, admin_user
):
    tokens = admin_login(admin_user.email).data
    api_client.force_authenticate(user=sysadmin)

    response = api_client.post(
        reverse("administrator-deactivate", args=[admin_user.pk])
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_active"] is False
    admin_user.refresh_from_db()
    assert admin_user.is_active is False

    # Cannot log in again.
    assert admin_login(admin_user.email).status_code == 400

    # An access token issued earlier no longer works.
    old_session = APIClient()
    old_session.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert old_session.get(reverse("current-user")).status_code == 401

    # The refresh token has been revoked.
    refreshed = APIClient().post(
        reverse("token-refresh"),
        {"refresh": tokens["refresh"]},
        format="json",
    )
    assert refreshed.status_code == 401


@pytest.mark.django_db
def test_activate_restores_login(api_client, sysadmin, admin_user):
    set_administrator_active(
        administrator=admin_user, actor=sysadmin, active=False
    )
    assert admin_login(admin_user.email).status_code == 400
    api_client.force_authenticate(user=sysadmin)

    response = api_client.post(
        reverse("administrator-activate", args=[admin_user.pk])
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_active"] is True
    assert admin_login(admin_user.email).status_code == 200


@pytest.mark.django_db
def test_deactivating_twice_is_harmless(api_client, sysadmin, admin_user):
    api_client.force_authenticate(user=sysadmin)
    url = reverse("administrator-deactivate", args=[admin_user.pk])

    assert api_client.post(url).status_code == 200
    assert api_client.post(url).status_code == 200


# ---- lock-out rules (service level) ---------------------------------------

@pytest.mark.django_db
def test_cannot_deactivate_own_account(sysadmin):
    make_user("second_sysadmin", User.Role.SYSTEM_ADMIN)

    with pytest.raises(ValidationError):
        set_administrator_active(
            administrator=sysadmin, actor=sysadmin, active=False
        )

    sysadmin.refresh_from_db()
    assert sysadmin.is_active is True


@pytest.mark.django_db
def test_cannot_deactivate_last_active_system_admin(sysadmin, admin_user):
    with pytest.raises(ValidationError, match="last active"):
        set_administrator_active(
            administrator=sysadmin, actor=admin_user, active=False
        )

    sysadmin.refresh_from_db()
    assert sysadmin.is_active is True


@pytest.mark.django_db
def test_can_deactivate_a_system_admin_when_another_remains(sysadmin):
    second = make_user("second_sysadmin", User.Role.SYSTEM_ADMIN)

    set_administrator_active(
        administrator=second, actor=sysadmin, active=False
    )

    second.refresh_from_db()
    assert second.is_active is False
