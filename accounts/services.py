from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .token_utils import revoke_user_tokens

User = get_user_model()


@transaction.atomic
def create_admin_account(**data):
    """Create an ADMIN account.

    The role and staff flag are set here, so no caller can choose them.
    """
    data.update(
        role=User.Role.ADMIN,
        is_staff=True,
        is_active=True,
    )
    return User.objects.create_user(**data)


@transaction.atomic
def set_administrator_active(*, administrator, actor, active):
    """Activate or deactivate an administrator account.

    Deactivating also revokes the account's refresh tokens. The rules that
    prevent lock-out live here so no endpoint can bypass them.
    """
    if administrator.is_active == active:
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
    administrator.save(update_fields=['is_active'])

    if not active:
        revoke_user_tokens(administrator)

    return administrator
