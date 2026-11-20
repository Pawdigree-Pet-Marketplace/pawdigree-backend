from decimal import Decimal

from django.conf import settings

from notification.models import Notification
from notification.services import create_notification, notify_admins

from .models import Order, VendorOrder

T = Notification.Type

STATUS_TEXT = {
    VendorOrder.Status.PROCESSING: "is being prepared",
    VendorOrder.Status.SHIPPED: "has been shipped",
    VendorOrder.Status.DELIVERED: "has been delivered. You can now leave a review",
}


def _money(value):
    return f"{settings.PAYMENT_CURRENCY} {value:,.0f}"


def notify_order_placed(order_id):
    order = Order.objects.select_related("customer").get(pk=order_id)
    create_notification(
        order.customer, T.ORDER_PLACED,
        f"Order #{order.pk} placed. Complete the payment before it expires.",
        reference_id=order.pk, reference_type="order",
        event_key=f"order-placed:{order.pk}",
    )


def notify_order_paid(order_id):
    """Customer: payment confirmed. Vendors: one notification per vendor
    order (and per kind: merchandise or pet) with the payment included."""
    order = (
        Order.objects.select_related("customer")
        .prefetch_related(
            "vendor_orders__business__vendor",
            "vendor_orders__items__product",
            "vendor_orders__items__pet",
        )
        .get(pk=order_id)
    )
    create_notification(
        order.customer, T.PAYMENT_CONFIRMED,
        f"Payment of {_money(order.total_amount)} confirmed for order #{order.pk}.",
        reference_id=order.pk, reference_type="order",
        event_key=f"order-paid:{order.pk}",
    )

    for vendor_order in order.vendor_orders.all():
        items = list(vendor_order.items.all())
        for kind, ntype, label in (
            ("product", T.NEW_ORDER, "New paid order"),
            ("pet", T.NEW_PET_SALE, "Pet sold"),
        ):
            chosen = [i for i in items if i.item_type == kind]
            if not chosen:
                continue
            names = ", ".join(
                f"{i.item_name} x{i.quantity}" if kind == "product" else i.item_name
                for i in chosen
            )
            total = sum((i.subtotal for i in chosen), Decimal("0"))
            create_notification(
                vendor_order.business.vendor, ntype,
                f"{label} #{order.pk}: {names}. Payment of {_money(total)} confirmed.",
                reference_id=vendor_order.pk, reference_type="vendor_order",
                business=vendor_order.business,
                event_key=f"{kind}-sale:{vendor_order.pk}",
            )


def notify_order_expired(order_id):
    order = Order.objects.select_related("customer").get(pk=order_id)
    create_notification(
        order.customer, T.ORDER_EXPIRED,
        f"Order #{order.pk} expired because it was not paid in time.",
        reference_id=order.pk, reference_type="order",
        event_key=f"order-expired:{order.pk}",
    )


def notify_status_changed(vendor_order_id, new_status):
    """Customer hears about each move; admins hear about a refund to pay."""
    vendor_order = VendorOrder.objects.select_related(
        "order__customer", "business"
    ).get(pk=vendor_order_id)
    customer = vendor_order.order.customer
    key = f"order-status:{vendor_order.pk}:{new_status}"

    if new_status == VendorOrder.Status.CANCELLED:
        create_notification(
            customer, T.ORDER_CANCELLED,
            f"Your order #{vendor_order.order_id} from {vendor_order.business.name} "
            "was cancelled. A refund will follow.",
            reference_id=vendor_order.order_id, reference_type="order",
            event_key=key,
        )
        notify_admins(
            T.REFUND_REQUIRED,
            f"Order #{vendor_order.order_id} was cancelled after payment: refund of "
            f"{_money(vendor_order.refund_amount)} is required.",
            reference_id=vendor_order.pk, reference_type="vendor_order",
            event_key=f"refund-required:{vendor_order.pk}",
        )
        return

    text = STATUS_TEXT.get(new_status)
    if text:
        create_notification(
            customer, T.ORDER_STATUS,
            f"Your order #{vendor_order.order_id} from {vendor_order.business.name} {text}.",
            reference_id=vendor_order.order_id, reference_type="order",
            event_key=key,
        )


def notify_refund_confirmed(vendor_order_id):
    vendor_order = VendorOrder.objects.select_related("order__customer").get(
        pk=vendor_order_id
    )
    create_notification(
        vendor_order.order.customer, T.REFUND_CONFIRMED,
        f"Your refund of {_money(vendor_order.refund_amount)} for order "
        f"#{vendor_order.order_id} has been sent.",
        reference_id=vendor_order.order_id, reference_type="order",
        event_key=f"refund-confirmed:{vendor_order.pk}",
    )