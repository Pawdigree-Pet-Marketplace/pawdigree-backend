from django.db import transaction

from accounts.models import User
from common.permissions import ADMIN_ROLES

from .models import Notification


def create_notification(
    user,
    notification_type,
    message,
    reference_id=None,
    reference_type="",
    business=None,
    event_key=None,
):
    """The one function every app uses to create a notification.

    Pass `event_key` for events that could fire twice (a payment webhook
    retried, a reminder job re-run). The same key and user creates only one
    notification; the existing one is returned.
    """
    fields = {
        "user": user,
        "type": notification_type,
        "message": message,
        "reference_type": reference_type,
        "reference_id": "" if reference_id is None else str(reference_id),
        "business_id": getattr(business, "pk", business),
    }
    if event_key:
        notification, _ = Notification.objects.get_or_create(
            event_key=f"{event_key}:u{user.pk}", defaults=fields
        )
        return notification
    return Notification.objects.create(**fields)


def notify_admins(notification_type, message, **kwargs):
    """Send the same notification to every active admin."""
    for admin in User.objects.filter(role__in=ADMIN_ROLES, is_active=True):
        create_notification(admin, notification_type, message, **kwargs)


def after_commit(func):
    """Run `func` once the surrounding transaction commits.

    A rolled-back action sends nothing. robust=True logs an error in `func`
    instead of raising it, so a notification bug can never undo a payment.
    """
    transaction.on_commit(func, robust=True)