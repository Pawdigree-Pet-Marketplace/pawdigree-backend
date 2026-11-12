from dataclasses import dataclass, field
from decimal import Decimal


class GatewayError(Exception):
    """The gateway could not be reached, refused a request, or sent a fake webhook."""


@dataclass(frozen=True)
class GatewayPayment:
    """What the gateway gives back when we start a payment."""

    transaction_id: str
    payment_url: str


@dataclass(frozen=True)
class GatewayEvent:
    """A payment result from the gateway, translated into our own terms."""

    reference: str
    transaction_id: str
    succeeded: bool
    amount: Decimal
    currency: str
    payload: dict = field(default_factory=dict)
    failure_reason: str = ""


class PaymentGateway:
    """Every gateway we support must implement these two methods."""

    def create_payment(self, payment, order):
        """Start a payment at the gateway and return a GatewayPayment."""
        raise NotImplementedError

    def read_webhook(self, request):
        """Verify the webhook is genuine and return a GatewayEvent.

        Raise GatewayError if the request is not genuine.
        """
        raise NotImplementedError