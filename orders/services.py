from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from cart.models import Cart
from cart.services import product_is_visible
from products.models import Product

from .models import Order, OrderItem, VendorOrder

TWO_PLACES = Decimal("0.01")

# How long a customer has to pay before the order expires.
CHECKOUT_WINDOW = timedelta(minutes=10)


def _release_locked(order, new_status):
    """Put an unpaid order's stock back and set its final status.

    The caller must already hold a lock on the order, inside
    transaction.atomic().
    """
    quantities = defaultdict(int)
    rows = OrderItem.objects.filter(vendor_order__order=order).values_list(
        "product_id", "quantity"
    )
    for product_id, quantity in rows:
        quantities[product_id] += quantity

    # Lock the products in a fixed order, so two requests can't wait on
    # each other forever.
    list(
        Product.objects.select_for_update()
        .filter(pk__in=list(quantities))
        .order_by("pk")
    )
    for product_id, quantity in quantities.items():
        Product.objects.filter(pk=product_id).update(
            stock_quantity=F("stock_quantity") + quantity
        )

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    order.vendor_orders.update(status=new_status, updated_at=timezone.now())


def checkout(customer, shipping):
    """Turn the customer's cart into an order that is waiting for payment.

    `shipping` is a dict with the keys shipping_name, shipping_phone,
    shipping_address, shipping_city_district and notes.

    One order is created for the whole checkout, with one vendor order per
    business. The stock is taken from the products now and given back if the
    order expires or is cancelled. The cart is left untouched until payment is
    confirmed. Everything happens in one transaction, so a refused checkout
    leaves nothing behind.
    """
    if customer.role != User.Role.CUSTOMER:
        raise PermissionDenied("Only customers can check out.")

    # Free the stock of payment windows that have run out, so it can be
    # bought in this checkout.
    expire_overdue_orders()

    with transaction.atomic():
        cart = Cart.objects.select_for_update().filter(customer=customer).first()
        if cart is None or not cart.items.exists():
            raise ValidationError({"cart": "Your cart is empty."})

        # A customer has one unpaid order at a time. Starting a new checkout
        # replaces the old one. If this checkout is refused, the old order
        # stays, because the whole transaction is rolled back.
        unpaid_orders = Order.objects.select_for_update().filter(
            customer=customer,
            status=Order.Status.PENDING_PAYMENT,
        )
        for unpaid in unpaid_orders:
            _release_locked(unpaid, Order.Status.CANCELLED)

        cart_items = list(cart.items.all())

        # Lock every product in the cart, in a fixed order. Nobody else can
        # buy them until this transaction ends, so the stock check below
        # stays true.
        products = {
            product.pk: product
            for product in Product.objects.select_for_update(of=("self",))
            .select_related("business", "category")
            .filter(pk__in=[item.product_id for item in cart_items])
            .order_by("pk")
        }

        problems = []
        for item in cart_items:
            product = products[item.product_id]
            if not product_is_visible(product):
                problems.append(f"{product.name} is no longer available.")
            elif product.stock_quantity == 0:
                problems.append(f"{product.name} is out of stock.")
            elif item.quantity > product.stock_quantity:
                problems.append(
                    f"Only {product.stock_quantity} of {product.name} left in stock."
                )
        if problems:
            raise ValidationError({"items": problems})

        by_business = defaultdict(list)
        for item in cart_items:
            by_business[products[item.product_id].business_id].append(item)

        subtotal = sum(
            (products[item.product_id].price * item.quantity for item in cart_items),
            Decimal("0.00"),
        ).quantize(TWO_PLACES)

        order = Order.objects.create(
            customer=customer,
            items_subtotal=subtotal,
            total_amount=subtotal,
            expires_at=timezone.now() + CHECKOUT_WINDOW,
            **shipping,
        )

        for business_id, items in by_business.items():
            vendor_order = VendorOrder.objects.create(
                order=order,
                business_id=business_id,
            )
            for item in items:
                product = products[item.product_id]
                OrderItem.objects.create(
                    vendor_order=vendor_order,
                    product=product,
                    quantity=item.quantity,
                    unit_price=product.price,
                )
                Product.objects.filter(pk=product.pk).update(
                    stock_quantity=F("stock_quantity") - item.quantity
                )

        return order


def cancel_unpaid_order(order_id):
    """Cancel an order that is still waiting for payment and release its stock.

    The payment code calls this when a payment fails. An order that is
    already paid, cancelled or expired is returned as it is, so calling this
    twice is harmless.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            raise NotFound("Order not found.")

        if order.status == Order.Status.PENDING_PAYMENT:
            _release_locked(order, Order.Status.CANCELLED)
        return order


def expire_overdue_orders():
    """Expire every unpaid order whose payment window has run out and release
    its stock. Returns how many orders were expired."""
    overdue_ids = list(
        Order.objects.filter(
            status=Order.Status.PENDING_PAYMENT,
            expires_at__lt=timezone.now(),
        ).values_list("pk", flat=True)
    )

    expired = 0
    for order_id in overdue_ids:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            # Check again under the lock, in case it was paid in the meantime.
            if (
                order is not None
                and order.status == Order.Status.PENDING_PAYMENT
                and order.expires_at is not None
                and order.expires_at < timezone.now()
            ):
                _release_locked(order, Order.Status.EXPIRED)
                expired += 1
    return expired