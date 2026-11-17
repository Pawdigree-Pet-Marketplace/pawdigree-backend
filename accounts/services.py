from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from audit.services import record as record_audit

from .admin_invites import send_admin_invite
from .models import AdminAuditLog
from .token_utils import revoke_user_tokens

User = get_user_model()

AUDIT_ACTIONS = {
    AdminAuditLog.Action.SYSTEM_ADMIN_CREATED: 'system_admin.created',
    AdminAuditLog.Action.ADMIN_CREATED: 'admin.created',
    AdminAuditLog.Action.ADMIN_ACTIVATED: 'admin.activated',
    AdminAuditLog.Action.ADMIN_DEACTIVATED: 'admin.deactivated',
}


def record_admin_action(*, actor, target, action):
    """Write one audit entry. Call this inside the action's transaction.

    `actor` is None for actions run from the server, such as the
    create_system_admin command.
    """
    entry = AdminAuditLog.objects.create(
        actor=actor,
        actor_email=actor.email if actor else '',
        target=target,
        target_email=target.email,
        action=action,
    )
    # Also write the general audit log that administrators can browse.
    record_audit(
        actor=actor,
        action=AUDIT_ACTIONS[action],
        target=target,
        details={'target_email': target.email},
    )
    return entry


@transaction.atomic
def create_admin_account(*, actor, **data):
    """Create an ADMIN account and record who created it.

    The role and staff flag are set here, so no caller can choose them.
    With no password given the account can't be used yet, and the admin is
    emailed a one-time link to set one. The email goes out after the
    transaction commits.
    """
    data.update(
        role=User.Role.ADMIN,
        is_staff=True,
        is_active=True,
    )
    administrator = User.objects.create_user(**data)
    record_admin_action(
        actor=actor,
        target=administrator,
        action=AdminAuditLog.Action.ADMIN_CREATED,
    )
    if not administrator.has_usable_password():
        transaction.on_commit(lambda: send_admin_invite(administrator))
    return administrator


@transaction.atomic
def set_administrator_active(*, administrator, actor, active):
    """Activate or deactivate an administrator account.

    Deactivating also revokes the account's refresh tokens. The rules that
    prevent lock-out live here so no endpoint can bypass them. A repeat
    request that changes nothing is not recorded.
    """
    target_status = (
        User.AccountStatus.ACTIVE
        if active
        else User.AccountStatus.DEACTIVATED
    )
    if (
        administrator.is_active == active
        and administrator.status == target_status
    ):
        return administrator

    if not active:
        if administrator.pk == actor.pk:
            raise ValidationError('You cannot deactivate your own account.')

        if administrator.role == User.Role.SYSTEM_ADMIN:
            other_active = list(
                User.objects.select_for_update()
                .filter(role=User.Role.SYSTEM_ADMIN, is_active=True)
                .exclude(pk=administrator.pk)
                .values_list('pk', flat=True)
            )
            if not other_active:
                raise ValidationError(
                    'The last active SYSTEM_ADMIN cannot be deactivated.'
                )

    administrator.is_active = active
    administrator.status = target_status
    administrator.save(update_fields=['is_active', 'status'])

    if not active:
        revoke_user_tokens(administrator)

    record_admin_action(
        actor=actor,
        target=administrator,
        action=(
            AdminAuditLog.Action.ADMIN_ACTIVATED
            if active
            else AdminAuditLog.Action.ADMIN_DEACTIVATED
        ),
    )
    return administrator


@transaction.atomic
def set_managed_user_active(*, user_id, actor, active):
    """Activate or deactivate an eligible customer or vendor account."""
    return set_managed_user_status(
        user_id=user_id,
        actor=actor,
        status=(
            User.AccountStatus.ACTIVE
            if active
            else User.AccountStatus.DEACTIVATED
        ),
    )


@transaction.atomic
def set_managed_user_status(*, user_id, actor, status, reason=None):
    """Set an eligible customer or vendor's account status atomically."""
    if actor.pk == user_id:
        raise ValidationError('You cannot change your own account status.')

    try:
        user = (
            User.objects.select_for_update()
            .get(
                pk=user_id,
                role__in=(User.Role.CUSTOMER, User.Role.VENDOR),
                is_superuser=False,
            )
        )
    except User.DoesNotExist:
        raise NotFound('User not found.')

    active = status == User.AccountStatus.ACTIVE
    if user.status == status and user.is_active == active:
        return user

    previous_status = user.status
    user.status = status
    user.is_active = active
    user.save(update_fields=['status', 'is_active'])

    if not active:
        revoke_user_tokens(user)

    record_audit(
        actor=actor,
        action={
            User.AccountStatus.ACTIVE: 'user.activated',
            User.AccountStatus.DEACTIVATED: 'user.deactivated',
            User.AccountStatus.SUSPENDED: 'user.suspended',
        }[status],
        target=user,
        details={
            'from_status': previous_status,
            'to_status': status,
            **({'reason': reason} if reason is not None else {}),
        },
    )
    return user
