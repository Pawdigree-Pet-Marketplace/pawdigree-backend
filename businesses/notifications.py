import logging

from notification.models import Notification
from notification.services import create_notification

from .models import Business

logger = logging.getLogger(__name__)

STATUS_TEXT = {
    Business.VerificationStatus.APPROVED: "was approved. You can now list your items.",
    Business.VerificationStatus.REJECTED: "was not approved. Open your business page for details.",
    Business.VerificationStatus.CHANGES_REQUESTED: "needs changes before it can be approved.",
    Business.VerificationStatus.SUSPENDED: "was suspended. Open your business page for details.",
}


def notify_business_status(business):
    text = STATUS_TEXT.get(business.verification_status)
    if text is None:
        return
    try:
        create_notification(
            business.vendor, Notification.Type.BUSINESS_VERIFICATION,
            f"Your business '{business.name}' {text}",
            reference_id=business.pk, reference_type="business", business=business,
        )
    except Exception:
        logger.exception("Could not notify vendor about business %s", business.pk)