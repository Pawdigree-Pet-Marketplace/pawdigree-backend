from cart.services import pet_is_buyable
from pets.models import Pet
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from audit.services import record as record_audit
from cart.models import Cart, CartItem
from cart.services import product_is_visible
from common.permissions import ADMIN_ROLES
from products.models import Product

from notification.services import after_commit
from .notifications import (
    notify_order_expired, notify_order_paid, notify_order_placed,
    notify_refund_confirmed, notify_status_changed,
)

from .models import Order, OrderItem, VendorOrder

TWO_PLACES = Decimal("0.01")

# How long a customer has to pay before the order expires.
CHECKOUT_WINDOW = timedelta(minutes=10)


def _restock(rows):
    """Put stock back. `rows` is an iterable of (product_id, quantity).

    The caller must already hold a lock on the order, inside
    transaction.atomic().
    """
    quantities = defaultdict(int)
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


def _release_pets(pet_ids):
    """Make reserved pets available again. Only RESERVED pets are touched,
    so a SOLD pet is never freed by mistake."""
    pet_ids = list(pet_ids)
    if not pet_ids:
        return
    list(Pet.objects.select_for_update().filter(pk__in=pet_ids).order_by("pk"))
    Pet.objects.filter(
        pk__in=pet_ids, adoption_status=Pet.AdoptionStatus.RESERVED
    ).update(adoption_status=Pet.AdoptionStatus.AVAILABLE)


def _release_locked(order, new_status):
    """Put an unpaid order's stock back and set its final status.

    The caller must already hold a lock on the order, inside
    transaction.atomic().
    """
    _restock(
        OrderItem.objects.filter(
            vendor_order__order=order, product__isnull=False
        ).values_list("product_id", "quantity")
    )

    _release_pets(
        OrderItem.objects.filter(
            vendor_order__order=order, pet__isnull=False
        ).values_list("pet_id", flat=True)
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
        pet_items = [item for item in cart_items if item.pet_id]
        cart_items = [item for item in cart_items if item.product_id]

        # Lock every pet in the cart, in a fixed order, so two customers
        # cannot buy the same animal.
        pets = {
            pet.pk: pet
            for pet in Pet.objects.select_for_update(of=("self",))
            .select_related("business")
            .filter(pk__in=[item.pet_id for item in pet_items])
            .order_by("pk")
        }

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
        for item in pet_items:
            pet = pets[item.pet_id]
            if not pet_is_buyable(pet):
                problems.append(f"{pet.name} is no longer available.")
        if problems:
            raise ValidationError({"items": problems})

        by_business = defaultdict(list)
        for item in cart_items:
            by_business[products[item.product_id].business_id].append(item)
        for item in pet_items:
            by_business[pets[item.pet_id].business_id].append(item)

        subtotal = sum(
            (
                (
                    products[item.product_id].price
                    if item.product_id
                    else pets[item.pet_id].price
                )
                * item.quantity
                for item in cart_items + pet_items
            ),
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
                if item.pet_id:
                    pet = pets[item.pet_id]
                    OrderItem.objects.create(
                        vendor_order=vendor_order,
                        pet=pet,
                        quantity=1,
                        unit_price=pet.price,
                    )
                    Pet.objects.filter(pk=pet.pk).update(
                        adoption_status=Pet.AdoptionStatus.RESERVED
                    )
                    continue
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

        after_commit(lambda: notify_order_placed(order.pk))
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
                after_commit(lambda oid=order.pk: notify_order_expired(oid))
    return expired

def mark_paid(order_id):
    """Record that an order has been paid.

    The payment code calls this once the gateway confirms the payment. The
    order and all its vendor orders become PAID, and the products that were
    bought leave the customer's cart. The stock was already taken at
    checkout, so it stays as it is.

    An order that is already paid is returned unchanged, so a payment
    confirmed twice is harmless. A cancelled or expired order is refused,
    because its stock has already been given back: the caller must treat
    that payment as one to refund.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            raise NotFound("Order not found.")

        if order.status == Order.Status.PAID:
            return order

        if order.status != Order.Status.PENDING_PAYMENT:
            raise ValidationError(
                {"order": "This order can no longer be paid: it was cancelled or expired."}
            )

        order.status = Order.Status.PAID
        order.save(update_fields=["status", "updated_at"])
        order.vendor_orders.update(
            status=VendorOrder.Status.PAID,
            updated_at=timezone.now(),
        )

        # Remove only what was bought. Anything the customer added to the
        # cart after checkout stays.
        bought_product_ids = OrderItem.objects.filter(
            vendor_order__order=order
        ).values_list("product_id", flat=True)
        CartItem.objects.filter(
            cart__customer=order.customer,
            product_id__in=list(bought_product_ids),
        ).delete()

        # Pets that were paid for are sold and leave the cart.
        bought_pet_ids = list(
            OrderItem.objects.filter(
                vendor_order__order=order, pet__isnull=False
            ).values_list("pet_id", flat=True)
        )
        if bought_pet_ids:
            list(
                Pet.objects.select_for_update()
                .filter(pk__in=bought_pet_ids)
                .order_by("pk")
            )
            Pet.objects.filter(pk__in=bought_pet_ids).update(
                adoption_status=Pet.AdoptionStatus.SOLD
            )
            CartItem.objects.filter(
                cart__customer=order.customer, pet_id__in=bought_pet_ids
            ).delete()
        
        after_commit(lambda: notify_order_paid(order.pk))
        return order


# Where a vendor order can go once it is paid. Vendors and admins can only
# set these statuses; the payment code sets PAID, CANCELLED and EXPIRED on
# unpaid orders.
_S = VendorOrder.Status
MANUAL_TRANSITIONS = {
    _S.PAID.value: (_S.PROCESSING.value, _S.CANCELLED.value),
    _S.PROCESSING.value: (_S.SHIPPED.value, _S.CANCELLED.value),
    _S.SHIPPED.value: (_S.DELIVERED.value,),
}


def change_status(vendor_order_id, new_status, actor, reason=""):
    """Move a paid vendor order to its next status.

    A vendor can only change orders of their own businesses. Admins and
    system admins can change any. An order that is not paid, or a move that
    is not in MANUAL_TRANSITIONS, is refused. Cancelling gives the stock
    back; the refund itself is handled by a person.
    """
    if actor.role not in (*ADMIN_ROLES, User.Role.VENDOR):
        raise PermissionDenied("You cannot change order statuses.")

    with transaction.atomic():
        vendor_order = (
            VendorOrder.objects.select_for_update(of=("self",))
            .select_related("order", "business")
            .filter(pk=vendor_order_id)
            .first()
        )
        # A vendor gets "not found" for other vendors' orders, so they
        # cannot tell whether an order exists.
        if vendor_order is None or (
            actor.role == User.Role.VENDOR
            and vendor_order.business.vendor_id != actor.pk
        ):
            raise NotFound("Order not found.")

        if vendor_order.order.status != Order.Status.PAID:
            raise ValidationError({"status": "This order has not been paid."})

        if new_status not in MANUAL_TRANSITIONS.get(vendor_order.status, ()):
            raise ValidationError(
                {
                    "status": (
                        f"An order that is {vendor_order.get_status_display().lower()} "
                        f"cannot be changed to {new_status.lower()}."
                    )
                }
            )

        if new_status == _S.CANCELLED:
            _restock(
                OrderItem.objects.filter(
                    vendor_order=vendor_order, product__isnull=False
                ).values_list("product_id", "quantity")
            )

        previous_status = vendor_order.status
        update_fields = ["status", "updated_at"]
        vendor_order.status = new_status

        if new_status == _S.CANCELLED:
            # The order was paid, so the customer is owed this portion back.
            vendor_order.refund_status = VendorOrder.RefundStatus.REQUIRED
            vendor_order.refund_amount = sum(
                (item.subtotal for item in vendor_order.items.all()),
                Decimal("0.00"),
            ).quantize(TWO_PLACES)
            vendor_order.cancelled_at = timezone.now()
            vendor_order.cancelled_by = actor
            vendor_order.cancel_reason = (reason or "")[:500]
            update_fields += [
                "refund_status",
                "refund_amount",
                "cancelled_at",
                "cancelled_by",
                "cancel_reason",
            ]

        vendor_order.save(update_fields=update_fields)

        # Vendors updating their own orders is routine and stays out of the
        # log; changes made by an administrator, and every cancellation of a
        # paid order (it creates a refund), are recorded.
        if actor.role in ADMIN_ROLES or new_status == _S.CANCELLED:
            record_audit(
                actor=actor,
                action="order.status_changed",
                target=vendor_order,
                details={
                    "from_status": previous_status,
                    "to_status": new_status,
                    "order": str(vendor_order.order_id),
                },
            )

        after_commit(lambda: notify_status_changed(vendor_order.pk, new_status))
        return vendor_order


def mark_refunded(vendor_order_id, actor):
    """Confirm that an administrator has paid back a cancelled vendor order.

    Only a vendor order whose refund is REQUIRED can be marked REFUNDED.
    A pet in the order stays SOLD until this point, then goes back on sale.
    """
    if actor.role not in ADMIN_ROLES:
        raise PermissionDenied("Only an administrator can confirm a refund.")

    with transaction.atomic():
        vendor_order = (
            VendorOrder.objects.select_for_update(of=("self",))
            .select_related("order")
            .filter(pk=vendor_order_id)
            .first()
        )
        if vendor_order is None:
            raise NotFound("Order not found.")

        if vendor_order.refund_status != VendorOrder.RefundStatus.REQUIRED:
            raise ValidationError(
                {"refund_status": "This order does not need a refund."}
            )

        vendor_order.refund_status = VendorOrder.RefundStatus.REFUNDED
        vendor_order.save(update_fields=["refund_status", "updated_at"])

        pet_ids = list(
            OrderItem.objects.filter(
                vendor_order=vendor_order, pet__isnull=False
            ).values_list("pet_id", flat=True)
        )
        if pet_ids:
            list(
                Pet.objects.select_for_update()
                .filter(pk__in=pet_ids)
                .order_by("pk")
            )
            Pet.objects.filter(
                pk__in=pet_ids, adoption_status=Pet.AdoptionStatus.SOLD
            ).update(adoption_status=Pet.AdoptionStatus.AVAILABLE)

        record_audit(
            actor=actor,
            action="order.refund_confirmed",
            target=vendor_order,
            details={
                "amount": str(vendor_order.refund_amount),
                "order": str(vendor_order.order_id),
            },
        )
        
        after_commit(lambda: notify_refund_confirmed(vendor_order.pk))
        return vendor_order
