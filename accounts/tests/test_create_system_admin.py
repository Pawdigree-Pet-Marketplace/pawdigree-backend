from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.management.commands import create_system_admin

User = get_user_model()

PASSWORD = "StrongPass123!"


def run_interactive(monkeypatch, email, password=PASSWORD, confirm=None, out=None):
    monkeypatch.setattr("builtins.input", lambda _="": email)
    answers = iter([password, password if confirm is None else confirm])
    monkeypatch.setattr(create_system_admin, "getpass", lambda _="": next(answers))
    call_command("create_system_admin", stdout=out or StringIO())


def system_admin_count():
    return User.objects.filter(role=User.Role.SYSTEM_ADMIN).count()


@pytest.mark.django_db
def test_creates_system_admin_with_correct_flags(monkeypatch):
    run_interactive(monkeypatch, "Boss@Example.com")

    user = User.objects.get(email="boss@example.com")
    assert user.role == User.Role.SYSTEM_ADMIN
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.is_email_verified is True
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD


@pytest.mark.django_db
def test_invalid_email_is_rejected(monkeypatch):
    with pytest.raises(CommandError):
        run_interactive(monkeypatch, "not-an-email")
    assert system_admin_count() == 0


@pytest.mark.django_db
def test_password_mismatch_is_rejected(monkeypatch):
    with pytest.raises(CommandError, match="do not match"):
        run_interactive(monkeypatch, "boss@example.com", confirm="Different123!")
    assert system_admin_count() == 0


@pytest.mark.django_db
def test_weak_password_is_rejected(monkeypatch):
    with pytest.raises(CommandError):
        run_interactive(monkeypatch, "boss@example.com", password="123")
    assert system_admin_count() == 0


@pytest.mark.django_db
def test_existing_email_is_not_touched(monkeypatch):
    customer = User.objects.create_user(
        username="existing_customer",
        email="Taken@Example.com",
        password="OldPass123!",
        role=User.Role.CUSTOMER,
    )

    with pytest.raises(CommandError, match="already exists"):
        run_interactive(monkeypatch, "taken@example.com")

    customer.refresh_from_db()
    assert customer.role == User.Role.CUSTOMER
    assert customer.check_password("OldPass123!")
    assert system_admin_count() == 0


@pytest.mark.django_db
def test_running_twice_does_not_create_a_second_system_admin(monkeypatch):
    run_interactive(monkeypatch, "first@example.com")

    out = StringIO()
    run_interactive(monkeypatch, "second@example.com", out=out)

    assert system_admin_count() == 1
    assert "already exists" in out.getvalue()
    assert not User.objects.filter(email="second@example.com").exists()


@pytest.mark.django_db
def test_noinput_creates_system_admin_from_environment(monkeypatch):
    monkeypatch.setenv("SYSTEM_ADMIN_EMAIL", "env@example.com")
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", PASSWORD)

    call_command("create_system_admin", "--noinput", stdout=StringIO())

    user = User.objects.get(email="env@example.com")
    assert user.role == User.Role.SYSTEM_ADMIN
    assert user.check_password(PASSWORD)


@pytest.mark.django_db
def test_noinput_without_environment_variables_fails(monkeypatch):
    monkeypatch.delenv("SYSTEM_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="SYSTEM_ADMIN_EMAIL"):
        call_command("create_system_admin", "--noinput", stdout=StringIO())
    assert system_admin_count() == 0


@pytest.mark.django_db
def test_noinput_is_safe_to_repeat(monkeypatch):
    monkeypatch.setenv("SYSTEM_ADMIN_EMAIL", "env@example.com")
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", PASSWORD)

    call_command("create_system_admin", "--noinput", stdout=StringIO())
    call_command("create_system_admin", "--noinput", stdout=StringIO())

    assert system_admin_count() == 1


@pytest.mark.django_db
def test_created_system_admin_can_log_in_through_admin_login(monkeypatch):
    run_interactive(monkeypatch, "boss@example.com")

    response = APIClient().post(
        reverse("admin-login"),
        {"email": "boss@example.com", "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.data
