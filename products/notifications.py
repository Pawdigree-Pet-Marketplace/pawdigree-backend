import logging

from django.conf import settings
from django.core.mail import send_mail

from notification.models import Notification
from notification.services import create_notification

logger = logging.getLogger(__name__)


def _notify(product, notification_type, message, email_subject):
    vendor = product.business.vendor

    try:
        create_notification(
            user=vendor, 
            notification_type=notification_type, 
            message=message,
            reference_id=product.pk, 
            reference_type="product", 
            business=product.business
            )
    except Exception:
        logger.exception(
            "Could not create notification for product %s", product.pk
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
        logger.exception("Could not email vendor about product %s", product.pk)


def notify_listing_approved(product):
    _notify(
        product,
        Notification.Type.LISTING_APPROVED,
        f"Your product '{product.name}' was approved and is now live on Pawdigree.",
        f"Your product '{product.name}' was approved",
    )


def notify_listing_rejected(product):
    _notify(
        product,
        Notification.Type.LISTING_REJECTED,
        (
            f"Your product '{product.name}' was not approved. "
            f"Reason: {product.rejection_reason} "
            "Edit the product to fix this and it will be reviewed again."
        ),
        f"Your product '{product.name}' needs changes",
    )
