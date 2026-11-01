from django.contrib.auth import get_user_model
from django.db import transaction

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
