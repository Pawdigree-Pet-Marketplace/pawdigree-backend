from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.forms.models import model_to_dict
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts import services
from accounts.models import AdminAuditLog
from accounts.services import create_admin_account, set_administrator_active

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


def admin_payload(**overrides):
    payload = {
        "username": "audited_admin",
        "first_name": "Audited",
        "last_name": "Admin",
        "email": "audited_admin@example.com",
        "phone": "0700000021",
        "password": PASSWORD,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sysadmin(db):
    return make_user("audit_sysadmin", User.Role.SYSTEM_ADMIN)


@pytest.fixture
def admin_user(db):
    return make_user("audit_target", User.Role.ADMIN, is_staff=True)


# ---- creation --------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["administrator-list", "admin-register"])
def test_creating_an_admin_is_recorded(api_client, sysadmin, url_name):
    api_client.force_authenticate(user=sysadmin)

    response = api_client.post(
        reverse(url_name), admin_payload(), format="json"
    )

    assert response.status_code == 201
    entry = AdminAuditLog.objects.get()
    created = User.objects.get(email="audited_admin@example.com")
    assert entry.action == AdminAuditLog.Action.ADMIN_CREATED
    assert entry.actor == sysadmin
    assert entry.actor_email == sysadmin.email
    assert entry.target == created
    assert entry.target_email == created.email
    assert entry.created_at is not None


@pytest.mark.django_db
def test_failed_creation_leaves_no_record(api_client, sysadmin, admin_user):
    api_client.force_authenticate(user=sysadmin)

    response = api_client.post(
        reverse("administrator-list"),
        admin_payload(email=admin_user.email),
        format="json",
    )

    assert response.status_code == 400
    assert AdminAuditLog.objects.count() == 0


@pytest.mark.django_db
def test_account_is_not_created_if_the_audit_write_fails(
    monkeypatch, sysadmin
):
    def broken_record(**kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(services, "record_admin_action", broken_record)

    with pytest.raises(RuntimeError):
        create_admin_account(actor=sysadmin, **admin_payload())

    assert not User.objects.filter(email="audited_admin@example.com").exists()


# ---- activate and deactivate -----------------------------------------------

@pytest.mark.django_db
def test_deactivate_and_activate_are_recorded(
    api_client, sysadmin, admin_user
):
    api_client.force_authenticate(user=sysadmin)

    api_client.post(reverse("administrator-deactivate", args=[admin_user.pk]))
    api_client.post(reverse("administrator-activate", args=[admin_user.pk]))

    entries = list(AdminAuditLog.objects.order_by("id"))
    assert [e.action for e in entries] == [
        AdminAuditLog.Action.ADMIN_DEACTIVATED,
        AdminAuditLog.Action.ADMIN_ACTIVATED,
    ]
    for entry in entries:
        assert entry.actor == sysadmin
        assert entry.target == admin_user
        assert entry.target_email == admin_user.email


@pytest.mark.django_db
def test_repeating_a_status_change_is_not_recorded_twice(
    api_client, sysadmin, admin_user
):
    api_client.force_authenticate(user=sysadmin)
    url = reverse("administrator-deactivate", args=[admin_user.pk])

    api_client.post(url)
    api_client.post(url)

    assert AdminAuditLog.objects.count() == 1


@pytest.mark.django_db
def test_blocked_deactivation_is_not_recorded(sysadmin, admin_user):
    with pytest.raises(ValidationError):
        set_administrator_active(
            administrator=sysadmin, actor=admin_user, active=False
        )
    with pytest.raises(ValidationError):
        set_administrator_active(
            administrator=sysadmin, actor=sysadmin, active=False
        )

    assert AdminAuditLog.objects.count() == 0


# ---- bootstrap -------------------------------------------------------------

@pytest.mark.django_db
def test_bootstrap_command_is_recorded_without_an_actor(monkeypatch):
    monkeypatch.setenv("SYSTEM_ADMIN_EMAIL", "first@example.com")
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", PASSWORD)

    call_command("create_system_admin", "--noinput", stdout=StringIO())
    call_command("create_system_admin", "--noinput", stdout=StringIO())

    entry = AdminAuditLog.objects.get()
    assert entry.action == AdminAuditLog.Action.SYSTEM_ADMIN_CREATED
    assert entry.actor is None
    assert entry.actor_email == ""
    assert entry.target_email == "first@example.com"


# ---- what the log may and may not hold -------------------------------------

@pytest.mark.django_db
def test_credentials_are_never_recorded(api_client, sysadmin):
    api_client.force_authenticate(user=sysadmin)
    api_client.post(
        reverse("administrator-list"), admin_payload(), format="json"
    )
    api_client.post(
        reverse(
            "administrator-deactivate",
            args=[User.objects.get(email="audited_admin@example.com").pk],
        )
    )

    field_names = [f.name for f in AdminAuditLog._meta.get_fields()]
    assert not any(
        word in name
        for name in field_names
        for word in ("password", "token", "secret")
    )

    for entry in AdminAuditLog.objects.all():
        stored = str(model_to_dict(entry))
        assert PASSWORD not in stored
        assert "pbkdf2" not in stored
        assert "Bearer" not in stored


@pytest.mark.django_db
def test_record_survives_deletion_of_the_account(sysadmin, admin_user):
    set_administrator_active(
        administrator=admin_user, actor=sysadmin, active=False
    )
    email = admin_user.email

    admin_user.delete()

    entry = AdminAuditLog.objects.get()
    assert entry.target is None
    assert entry.target_email == email
