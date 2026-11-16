import pytest

from accounts.models import AdminAuditLog
from accounts.services import record_admin_action, set_administrator_active
from audit.models import AuditLog


@pytest.mark.django_db
def test_deactivate_and_activate_are_in_the_audit_log(system_admin, admin):
    set_administrator_active(
        administrator=admin, actor=system_admin, active=False
    )
    set_administrator_active(
        administrator=admin, actor=system_admin, active=True
    )

    entries = list(AuditLog.objects.order_by('id'))
    assert [e.action for e in entries] == [
        'admin.deactivated',
        'admin.activated',
    ]
    assert entries[0].actor == system_admin
    assert entries[0].actor_role == system_admin.role
    assert entries[0].target_id == str(admin.pk)
    assert entries[0].details == {'target_email': admin.email}


@pytest.mark.django_db
def test_repeat_request_that_changes_nothing_is_not_recorded(
    system_admin, admin
):
    set_administrator_active(
        administrator=admin, actor=system_admin, active=True
    )

    assert AuditLog.objects.count() == 0
    assert AdminAuditLog.objects.count() == 0


@pytest.mark.django_db
def test_server_side_creation_has_no_actor(admin):
    record_admin_action(
        actor=None,
        target=admin,
        action=AdminAuditLog.Action.SYSTEM_ADMIN_CREATED,
    )

    entry = AuditLog.objects.get()
    assert entry.action == 'system_admin.created'
    assert entry.actor is None
    assert entry.actor_email == ''
    assert AdminAuditLog.objects.count() == 1
