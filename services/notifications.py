import logging

from django.conf import settings
from django.core.mail import send_mail

from notification.models import Notification
from notification.services import create_notification

logger = logging.getLogger(__name__)


def _notify(service, notification_type, message, email_subject):
    vendor = service.business.vendor

    try:
        create_notification(
            user=vendor,
            notification_type=notification_type,
            message=message,
            reference_id=service.pk,
        )
    except Exception:
        logger.exception(
            "Could not create notification for service %s", service.pk
        )

    # Email the vendor when their listing is approved or rejected.
    try:
        send_mail(
            email_subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [vendor.email],
        )
    except Exception:
        logger.exception("Could not email vendor about service %s", service.pk)


def notify_listing_approved(service):
    _notify(
        service,
        Notification.Type.LISTING_APPROVED,
        f"Your service '{service.name}' was approved and is now live on Pawdigree.",
        f"Your service '{service.name}' was approved",
    )


def notify_listing_rejected(service):
    _notify(
        service,
        Notification.Type.LISTING_REJECTED,
        (
            f"Your service '{service.name}' was not approved. "
            f"Reason: {service.rejection_reason} "
            "Edit the service to fix this and it will be reviewed again."
        ),
        f"Your service '{service.name}' needs changes",
    )
