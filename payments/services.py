import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from accounts.models import User
from orders.models import Order
from orders.services import cancel_unpaid_order, expire_overdue_orders, mark_paid

from .gateways import GatewayError, get_gateway
from .models import Payment
from notification.services import after_commit
from .notifications import notify_payment_failed, notify_payment_needs_refund


class PaymentGatewayUnavailable(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The payment service is unavailable. Please try again."
    default_code = "gateway_unavailable"


def start_payment(customer, order_id, method):
    """Start the payment for a customer's order and return the Payment.

    The amount always comes from the order, never from the request. Calling
    this twice for the same order returns the payment already started.
    """
    if customer.role != User.Role.CUSTOMER:
        raise PermissionDenied("Only customers can pay for orders.")

    if method not in settings.PAYMENT_METHODS:
        raise ValidationError({"method": "Choose a supported payment method."})

    # An order past its window must be refused here, not paid.
    expire_overdue_orders()

    with transaction.atomic():
        order = (Order.objects.select_for_update().filter(pk=order_id, customer=customer).first())
        if order is None:
            raise NotFound("Order not found.")

        if order.status != Order.Status.PENDING_PAYMENT:
            raise ValidationError({"order": "This order is not waiting for payment."})

        existing = Payment.objects.filter(order=order).first()
        if existing is not None:
            return existing

        payment = Payment.objects.create(
            order=order,
            method=method,
            amount=order.total_amount,
            currency=settings.PAYMENT_CURRENCY,
            gateway_reference=f"PAW-{order.pk}-{uuid.uuid4().hex[:8]}",
        )

        try:
            result = get_gateway().create_payment(payment, order)
        except GatewayError as exc:
            # Raising rolls back the Payment row, so a failed start leaves nothing behind.
            raise PaymentGatewayUnavailable() from exc

        payment.gateway_transaction_id = result.transaction_id
        payment.payment_url = result.payment_url
        payment.save(
            update_fields=["gateway_transaction_id", "payment_url", "updated_at"]
        )
        return payment


def process_gateway_event(event):
    """Apply a verified gateway result to the payment and its order.
    Safe to call many times with the same event: a payment that has already
    been settled is returned unchanged."""
    with transaction.atomic():
        payment = (Payment.objects.select_for_update(of=("self",)).filter(gateway_reference=event.reference).first())
        if payment is None:
            raise NotFound("Unknown payment reference.")

        if payment.status != Payment.Status.PENDING:
            return payment

        if event.transaction_id:
            payment.gateway_transaction_id = event.transaction_id
        payment.gateway_payload = event.payload

        if not event.succeeded:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = event.failure_reason[:255]
            payment.save()
            cancel_unpaid_order(payment.order_id)
            after_commit(lambda: notify_payment_failed(payment.order_id))
            return payment

        if event.amount != payment.amount or event.currency != payment.currency:
            payment.status = Payment.Status.REFUND_REQUIRED
            payment.failure_reason = "The amount paid did not match the order total."
            payment.save()
            cancel_unpaid_order(payment.order_id)
            after_commit(lambda: notify_payment_needs_refund(payment.pk))
            return payment

        try:
            mark_paid(payment.order_id)
        except ValidationError:
            payment.status = Payment.Status.REFUND_REQUIRED
            payment.failure_reason = ("Payment arrived after the order was cancelled or expired.")
            after_commit(lambda: notify_payment_needs_refund(payment.pk))
        else:
            payment.status = Payment.Status.PAID
            payment.paid_at = timezone.now()

        payment.save()
        
        return payment