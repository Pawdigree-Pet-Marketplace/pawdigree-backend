from django.conf import settings
from django.utils.module_loading import import_string

from .base import GatewayError, GatewayEvent, GatewayPayment, PaymentGateway

__all__ = ["GatewayError", "GatewayEvent", "GatewayPayment", "PaymentGateway", "get_gateway"]


def get_gateway():
    """Return the gateway chosen in settings."""
    return import_string(settings.PAYMENT_GATEWAY_CLASS)()