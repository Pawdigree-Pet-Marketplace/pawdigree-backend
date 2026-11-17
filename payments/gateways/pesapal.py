import json
import logging
from decimal import Decimal, InvalidOperation
import hashlib

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from .base import GatewayError, GatewayEvent, GatewayPayment, PaymentGateway

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
TOKEN_CACHE_KEY = "pesapal-bearer-token"
TOKEN_CACHE_SECONDS = 240

SUCCESS = "COMPLETED"
FAILURES = {"FAILED", "INVALID", "REVERSED"}


class PesapalGateway(PaymentGateway):
    """Takes payments through Pesapal's hosted checkout (API 3.0)."""

    def __init__(self):
        for name in (
            "PESAPAL_BASE_URL",
            "PESAPAL_CONSUMER_KEY",
            "PESAPAL_CONSUMER_SECRET",
        ):
            if not getattr(settings, name, ""):
                raise ImproperlyConfigured(f"{name} is not set.")
        self.base_url = settings.PESAPAL_BASE_URL.rstrip("/")

    def _request(self, method, path, token=None, **kwargs):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            body = getattr(getattr(exc, "response", None), "text", "")
            logger.error("Pesapal request to %s failed: %s %s", path, exc, body[:500])
            raise GatewayError("Pesapal request failed.") from exc

        error = data.get("error") if isinstance(data, dict) else True
        if isinstance(error, dict):
            error = any(error.values())
        if error:
            logger.error("Pesapal returned an error for %s: %s", path, data)
            raise GatewayError("Pesapal returned an error.")
        return data

    def _token(self):
        cache_key = (
            f"{TOKEN_CACHE_KEY}:"
            f"{hashlib.sha256(self.base_url.encode()).hexdigest()[:16]}"
        )
        token = cache.get(cache_key)
        if token:
            return token

        data = self._request(
            "post",
            "/Auth/RequestToken",
            json={
                "consumer_key": settings.PESAPAL_CONSUMER_KEY,
                "consumer_secret": settings.PESAPAL_CONSUMER_SECRET,
            },
        )
        token = data.get("token")
        if not token:
            raise GatewayError("Pesapal did not return a token.")

        cache.set(cache_key, token, TOKEN_CACHE_SECONDS)
        return token

    def register_ipn(self, url):
        """Register the webhook URL once. Returns the ipn_id to put in settings."""
        data = self._request(
            "post",
            "/URLSetup/RegisterIPN",
            token=self._token(),
            json={"url": url, "ipn_notification_type": "POST"},
        )
        return data.get("ipn_id")

    def create_payment(self, payment, order):
        if not settings.PESAPAL_IPN_ID:
            raise ImproperlyConfigured("PESAPAL_IPN_ID is not set.")

        customer = order.customer
        payload = {
            "id": payment.gateway_reference,
            "currency": payment.currency,
            "amount": float(payment.amount),
            "description": f"Pawdigree order #{order.pk}"[:100],
            "callback_url": settings.PESAPAL_CALLBACK_URL.format(order_id=order.pk),
            "notification_id": settings.PESAPAL_IPN_ID,
            "billing_address": {
                "email_address": customer.email,
                "phone_number": order.shipping_phone,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
            },
        }
        if settings.PESAPAL_CANCEL_URL:
            payload["cancellation_url"] = settings.PESAPAL_CANCEL_URL

        data = self._request(
            "post",
            "/Transactions/SubmitOrderRequest",
            token=self._token(),
            json=payload,
        )

        tracking_id = data.get("order_tracking_id")
        redirect_url = data.get("redirect_url")
        if not tracking_id or not redirect_url:
            raise GatewayError("Pesapal did not return a payment link.")

        return GatewayPayment(transaction_id=tracking_id, payment_url=redirect_url)

    def read_webhook(self, request):
        try:
            body = json.loads(request.body or b"{}")
        except ValueError as exc:
            raise GatewayError("Malformed webhook body.") from exc
        if not isinstance(body, dict):
            raise GatewayError("Malformed webhook body.")

        tracking_id = body.get("OrderTrackingId") or request.GET.get("OrderTrackingId")
        if not tracking_id:
            raise GatewayError("The webhook has no tracking id.")

        status = self._request(
            "get",
            "/Transactions/GetTransactionStatus",
            token=self._token(),
            params={"orderTrackingId": tracking_id},
        )

        state = str(status.get("payment_status_description", "")).upper()
        if state != SUCCESS and state not in FAILURES:
            raise GatewayError(f"The payment is not final yet: {state or 'unknown'}.")

        try:
            return GatewayEvent(
                reference=status["merchant_reference"],
                transaction_id=tracking_id,
                succeeded=state == SUCCESS,
                amount=Decimal(str(status["amount"])),
                currency=status["currency"],
                payload=status,
                failure_reason=(
                    "" if state == SUCCESS else str(status.get("description") or state)
                ),
            )
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise GatewayError("Unexpected Pesapal status response.") from exc

    def acknowledgement(self, event):
        return {
            "orderNotificationType": "IPNCHANGE",
            "orderTrackingId": event.transaction_id,
            "orderMerchantReference": event.reference,
            "status": 200,
        }