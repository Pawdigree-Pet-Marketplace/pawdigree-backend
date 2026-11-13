import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import GatewayError, GatewayEvent, GatewayPayment, PaymentGateway


class SandboxGateway(PaymentGateway):
    """A fake gateway for development. It never moves real money."""

    def __init__(self):
        if not settings.DEBUG:
            raise ImproperlyConfigured("The sandbox gateway only works when DEBUG is on.")

    @staticmethod
    def sign(body):
        """Return the signature for a webhook body (bytes)."""
        secret = settings.SANDBOX_WEBHOOK_SECRET.encode()
        return hmac.new(secret, body, hashlib.sha256).hexdigest()

    def create_payment(self, payment, order):
        return GatewayPayment(
            transaction_id=f"SBX-{payment.gateway_reference}",
            payment_url=(
                f"{settings.SANDBOX_PAYMENT_PAGE}"
                f"?reference={payment.gateway_reference}"
                f"&order_id={order.pk}"
            ),
        )

    def read_webhook(self, request):
        received = request.headers.get("X-Signature", "")
        if not hmac.compare_digest(received, self.sign(request.body)):
            raise GatewayError("Invalid webhook signature.")

        try:
            data = json.loads(request.body)
            return GatewayEvent(
                reference=data["reference"],
                transaction_id=data.get("transaction_id", ""),
                succeeded=data["status"] == "success",
                amount=Decimal(str(data["amount"])),
                currency=data["currency"],
                payload=data,
                failure_reason=data.get("reason", ""),
            )
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            raise GatewayError("Malformed webhook payload.") from exc