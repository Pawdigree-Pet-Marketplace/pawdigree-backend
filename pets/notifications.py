import logging

from django.conf import settings
from django.core.mail import send_mail

from notification.models import Notification
from notification.services import create_notification

logger = logging.getLogger(__name__)


def _notify(pet, notification_type, message, email_subject):
    try:
        create_notification(
            user=pet.vendor,
            notification_type=notification_type,
            message=message,
            reference_id=pet.pk,
        )
    except Exception:
        logger.exception("Could not create notification for pet %s", pet.pk)

#email notifications to the respective vendor when their listing is approved or rejected
    try:
        send_mail(
            email_subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [pet.vendor.email],
        )
    except Exception:
        logger.exception("Could not email vendor about pet %s", pet.pk)


def notify_listing_approved(pet):
    _notify(
        pet,
        Notification.Type.LISTING_APPROVED,
        f"Your listing '{pet.name}' was approved and is now live on Pawdigree.",
        f"Your listing '{pet.name}' was approved",
    )


def notify_listing_rejected(pet):
    _notify(
        pet,
        Notification.Type.LISTING_REJECTED,
        (
            f"Your listing '{pet.name}' was not approved. "
            f"Reason: {pet.rejection_reason} "
            "Edit the listing to fix this and it will be reviewed again."
        ),
        f"Your listing '{pet.name}' needs changes",
    )