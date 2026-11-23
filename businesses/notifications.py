import logging

from notification.models import Notification
from notification.services import create_notification

from .models import Business, BusinessDecision

logger = logging.getLogger(__name__)

DECISION_TEXT = {
    BusinessDecision.Action.APPROVE: "was approved. You can now list your items.",
    BusinessDecision.Action.REAPPROVE: "was reinstated. You can list your items again.",
    BusinessDecision.Action.REQUEST_CHANGES: (
        "needs changes before it can be approved. "
        "Open your business page for details."
    ),
    BusinessDecision.Action.SUSPEND: (
        "was suspended. Open your business page for details."
    ),
}


def notify_business_decision(business_id, action, decision_id):
    """Tell the vendor about an admin decision. Never breaks the decision itself."""
    text = DECISION_TEXT.get(action)
    if text is None:
        return
    try:
        business = Business.objects.select_related("vendor").get(pk=business_id)
        create_notification(
            business.vendor,
            Notification.Type.BUSINESS_VERIFICATION,
            f"Your business '{business.name}' {text}",
            reference_id=str(business.pk),
            reference_type="business",
            business=business,
            # One notification per decision, even if the callback ever runs twice.
            event_key=f"business-decision:{decision_id}",
        )
    except Exception:
        logger.exception("Could not notify vendor about business %s", business_id)