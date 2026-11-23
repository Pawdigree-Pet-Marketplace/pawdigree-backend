"""Recording that an administrator paid a customer back for a payment.

The gateways have no refund call here: an administrator sends the money from
the gateway's own dashboard, then records it with this function. Checkout,
payment processing and the webhook are not touched.
"""

from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, ValidationError

from audit.services import record as record_audit

from .models import Payment, PaymentRefund

TWO_PLACES = Decimal("0.01")


def received_amount(payment):
    """The amount the gateway says it received, or None if it did not say."""
    payload = payment.gateway_payload
    if not isinstance(payload, dict) or payload.get("amount") is None:
        return None
    try:
        return Decimal(str(payload["amount"])).quantize(TWO_PLACES)
    except InvalidOperation:
        return None


def refund_limit(payment):
    """The most that can be paid back.

    The larger of the recorded amount and what the gateway says it received:
    they differ when the customer paid the wrong amount.
    """
    received = received_amount(payment)
    if received is None:
        return payment.amount
    return max(payment.amount, received)


def mark_payment_refunded(payment_id, actor, *, amount, gateway_reference, reason=""):
    """Record a refund and move the payment from REFUND_REQUIRED to REFUNDED.

    The payment row is locked, so two requests cannot both succeed, and the
    one-to-one link on PaymentRefund stops a second record at database level.
    """
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update(of=("self",))
            .select_related("order")
            .filter(pk=payment_id)
            .first()
        )
        if payment is None:
            raise NotFound("Payment not found.")

        if payment.status != Payment.Status.REFUND_REQUIRED:
            raise ValidationError({"status": "This payment does not need a refund."})

        if amount > refund_limit(payment):
            raise ValidationError({"amount": "The refund is more than was paid."})

        try:
            with transaction.atomic():
                refund = PaymentRefund.objects.create(
                    payment=payment,
                    refunded_by=actor,
                    amount=amount,
                    currency=payment.currency,
                    reason=reason,
                    gateway_reference=gateway_reference,
                )
        except IntegrityError:
            raise ValidationError(
                {"gateway_reference": "This refund reference was already recorded."}
            )

        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])

        record_audit(
            actor=actor,
            action="payment.refund_confirmed",
            target=payment,
            details={
                "amount": str(amount),
                "currency": payment.currency,
                "order": str(payment.order_id),
                "gateway_reference": gateway_reference,
            },
        )
        return refund
