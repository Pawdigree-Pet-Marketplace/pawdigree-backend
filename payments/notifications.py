from django.conf import settings

from notification.models import Notification
from notification.services import create_notification, notify_admins
from orders.models import Order

from .models import Payment

T = Notification.Type


def notify_payment_failed(order_id):
    """Failed payment: only the customer hears, and never a success message."""
    order = Order.objects.select_related("customer").get(pk=order_id)
    create_notification(
        order.customer, T.PAYMENT_FAILED,
        f"The payment for order #{order.pk} failed and the order was cancelled. "
        "Your cart is unchanged, so you can check out again.",
        reference_id=order.pk, reference_type="order",
        event_key=f"payment-failed:{order.pk}",
    )


def notify_payment_needs_refund(payment_id):
    """Money arrived that cannot be used (wrong amount or too late)."""
    payment = Payment.objects.select_related("order__customer").get(pk=payment_id)
    order = payment.order
    create_notification(
        order.customer, T.PAYMENT_FAILED,
        f"We could not complete order #{order.pk}: {payment.failure_reason} "
        "Your money will be refunded.",
        reference_id=order.pk, reference_type="order",
        event_key=f"payment-refund-customer:{payment.pk}",
    )
    notify_admins(
        T.REFUND_REQUIRED,
        f"Payment {payment.gateway_reference} needs a refund: {payment.failure_reason}",
        reference_id=order.pk, reference_type="order",
        event_key=f"payment-refund-admin:{payment.pk}",
    )