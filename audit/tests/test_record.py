import pytest

from audit.models import AuditLog
from audit.services import record


@pytest.mark.django_db
def test_record_stores_actor_target_and_details(admin, customer):
    entry = record(
        actor=admin,
        action='user.reviewed',
        target=customer,
        details={'reason': 'test'},
    )

    entry.refresh_from_db()
    assert entry.actor == admin
    assert entry.actor_email == admin.email
    assert entry.actor_role == admin.role
    assert entry.action == 'user.reviewed'
    assert entry.target_type == 'accounts.user'
    assert entry.target_id == str(customer.pk)
    assert entry.details == {'reason': 'test'}
    assert entry.created_at is not None


@pytest.mark.django_db
def test_record_without_actor_or_target():
    entry = record(actor=None, action='system.started')

    assert entry.actor is None
    assert entry.actor_email == ''
    assert entry.actor_role == ''
    assert entry.target_type == ''
    assert entry.target_id == ''
    assert entry.details == {}


@pytest.mark.django_db
def test_entry_survives_actor_deletion(admin):
    email = admin.email
    entry = record(actor=admin, action='thing.done')

    admin.delete()
    entry.refresh_from_db()

    assert entry.actor is None
    assert entry.actor_email == email
    assert AuditLog.objects.filter(pk=entry.pk).exists()
