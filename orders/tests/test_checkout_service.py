from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order, OrderItem, VendorOrder
from orders.services import (
    CHECKOUT_WINDOW,
    cancel_unpaid_order,
    checkout,
    expire_overdue_orders,
)

SHIPPING = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "",
}


class CheckoutServiceTests(TestCase):
    def setUp(self):
        self.customer = make_user("buyer1", User.Role.CUSTOMER)
        self.other_customer = make_user("buyer2", User.Role.CUSTOMER)
        self.vendor_one = make_user("seller1", User.Role.VENDOR)
        self.vendor_two = make_user("seller2", User.Role.VENDOR)
        self.business_one = make_business(self.vendor_one, name="Paws Place")
        self.business_two = make_business(self.vendor_two, name="Fur Shop")
        self.category = make_category()
        self.toy = make_product(
            self.business_one, self.category, name="Chew toy", price="10.00", stock=5
        )
        self.bed = make_product(
            self.business_two, self.category, name="Dog bed", price="25.50", stock=3
        )

    def add_to_cart(self, customer, product, quantity):
        cart, _ = Cart.objects.get_or_create(customer=customer)
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)

    def stock(self, product):
        product.refresh_from_db()
        return product.stock_quantity

    # ---- checkout ----------------------------------------------------

    def test_checkout_creates_order_for_one_vendor(self):
        self.add_to_cart(self.customer, self.toy, 2)
        before = timezone.now()

        order = checkout(self.customer, SHIPPING)

        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(order.items_subtotal, Decimal("20.00"))
        self.assertEqual(order.total_amount, Decimal("20.00"))
        self.assertEqual(order.shipping_name, "Jane Doe")
        self.assertEqual(order.shipping_phone, "+256700123456")
        self.assertAlmostEqual(
            order.expires_at.timestamp(),
            (before + CHECKOUT_WINDOW).timestamp(),
            delta=5,
        )

        vendor_order = order.vendor_orders.get()
        self.assertEqual(vendor_order.business, self.business_one)
        self.assertEqual(vendor_order.status, VendorOrder.Status.PENDING_PAYMENT)

        item = vendor_order.items.get()
        self.assertEqual(item.product, self.toy)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("10.00"))

    def test_checkout_reduces_stock(self):
        self.add_to_cart(self.customer, self.toy, 2)

        checkout(self.customer, SHIPPING)

        self.assertEqual(self.stock(self.toy), 3)

    def test_checkout_splits_products_into_one_vendor_order_per_business(self):
        self.add_to_cart(self.customer, self.toy, 2)
        self.add_to_cart(self.customer, self.bed, 1)

        order = checkout(self.customer, SHIPPING)

        self.assertEqual(order.vendor_orders.count(), 2)
        businesses = {vo.business for vo in order.vendor_orders.all()}
        self.assertEqual(businesses, {self.business_one, self.business_two})
        self.assertEqual(order.items_subtotal, Decimal("45.50"))
        self.assertEqual(order.total_amount, Decimal("45.50"))
        self.assertEqual(self.stock(self.toy), 3)
        self.assertEqual(self.stock(self.bed), 2)

    def test_checkout_leaves_the_cart_untouched(self):
        self.add_to_cart(self.customer, self.toy, 2)

        checkout(self.customer, SHIPPING)

        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.get().quantity, 2)

    def test_order_keeps_the_price_from_checkout_time(self):
        self.add_to_cart(self.customer, self.toy, 1)
        order = checkout(self.customer, SHIPPING)

        self.toy.price = Decimal("99.00")
        self.toy.save()

        item = OrderItem.objects.get(vendor_order__order=order)
        self.assertEqual(item.unit_price, Decimal("10.00"))

    def test_checkout_with_no_cart_is_refused(self):
        with self.assertRaises(ValidationError):
            checkout(self.customer, SHIPPING)

        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_with_empty_cart_is_refused(self):
        Cart.objects.create(customer=self.customer)

        with self.assertRaises(ValidationError):
            checkout(self.customer, SHIPPING)

        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_refused_when_out_of_stock(self):
        self.add_to_cart(self.customer, self.toy, 2)
        self.toy.stock_quantity = 0
        self.toy.save()

        with self.assertRaises(ValidationError):
            checkout(self.customer, SHIPPING)

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(self.toy), 0)

    def test_checkout_refused_when_not_enough_stock_and_nothing_changes(self):
        self.add_to_cart(self.customer, self.toy, 2)
        self.add_to_cart(self.customer, self.bed, 3)
        self.bed.stock_quantity = 1
        self.bed.save()

        with self.assertRaises(ValidationError):
            checkout(self.customer, SHIPPING)

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(self.toy), 5)
        self.assertEqual(self.stock(self.bed), 1)

    def test_checkout_refused_when_product_is_no_longer_visible(self):
        self.add_to_cart(self.customer, self.toy, 1)
        self.toy.is_active = False
        self.toy.save()

        with self.assertRaises(ValidationError):
            checkout(self.customer, SHIPPING)

        self.assertEqual(Order.objects.count(), 0)

    def test_only_customers_can_check_out(self):
        with self.assertRaises(PermissionDenied):
            checkout(self.vendor_one, SHIPPING)

    def test_new_checkout_replaces_the_unpaid_order(self):
        self.add_to_cart(self.customer, self.toy, 2)
        first = checkout(self.customer, SHIPPING)

        second = checkout(self.customer, SHIPPING)

        first.refresh_from_db()
        self.assertEqual(first.status, Order.Status.CANCELLED)
        self.assertEqual(
            first.vendor_orders.get().status, VendorOrder.Status.CANCELLED
        )
        self.assertEqual(second.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(
            Order.objects.filter(status=Order.Status.PENDING_PAYMENT).count(), 1
        )
        # The first order's stock went back, then the second took its own.
        self.assertEqual(self.stock(self.toy), 3)

    def test_refused_checkout_keeps_the_old_unpaid_order(self):
        self.add_to_cart(self.customer, self.toy, 2)
        first = checkout(self.customer, SHIPPING)
        # The cart now asks for more than the stock can cover.
        CartItem.objects.filter(cart__customer=self.customer).update(quantity=10)

        with self.assertRaises(ValidationError):
            checkout(self.customer, SHIPPING)

        first.refresh_from_db()
        self.assertEqual(first.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(self.stock(self.toy), 3)

    def test_checkout_can_use_stock_held_by_an_expired_order(self):
        self.add_to_cart(self.other_customer, self.toy, 5)
        held = checkout(self.other_customer, SHIPPING)
        Order.objects.filter(pk=held.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertEqual(self.stock(self.toy), 0)

        self.add_to_cart(self.customer, self.toy, 5)
        order = checkout(self.customer, SHIPPING)

        held.refresh_from_db()
        self.assertEqual(held.status, Order.Status.EXPIRED)
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(self.stock(self.toy), 0)

    # ---- cancel and expire --------------------------------------------

    def test_cancel_unpaid_order_releases_stock(self):
        self.add_to_cart(self.customer, self.toy, 2)
        self.add_to_cart(self.customer, self.bed, 1)
        order = checkout(self.customer, SHIPPING)

        cancelled = cancel_unpaid_order(order.pk)

        self.assertEqual(cancelled.status, Order.Status.CANCELLED)
        for vendor_order in order.vendor_orders.all():
            self.assertEqual(vendor_order.status, VendorOrder.Status.CANCELLED)
        self.assertEqual(self.stock(self.toy), 5)
        self.assertEqual(self.stock(self.bed), 3)

    def test_cancelling_twice_releases_stock_only_once(self):
        self.add_to_cart(self.customer, self.toy, 2)
        order = checkout(self.customer, SHIPPING)

        cancel_unpaid_order(order.pk)
        cancel_unpaid_order(order.pk)

        self.assertEqual(self.stock(self.toy), 5)

    def test_cancel_does_not_touch_a_paid_order(self):
        self.add_to_cart(self.customer, self.toy, 2)
        order = checkout(self.customer, SHIPPING)
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PAID)

        result = cancel_unpaid_order(order.pk)

        self.assertEqual(result.status, Order.Status.PAID)
        self.assertEqual(self.stock(self.toy), 3)

    def test_cancel_unknown_order_raises_not_found(self):
        with self.assertRaises(NotFound):
            cancel_unpaid_order(999999)

    def test_expire_overdue_orders_releases_stock(self):
        self.add_to_cart(self.customer, self.toy, 2)
        order = checkout(self.customer, SHIPPING)
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expired = expire_overdue_orders()

        order.refresh_from_db()
        self.assertEqual(expired, 1)
        self.assertEqual(order.status, Order.Status.EXPIRED)
        self.assertEqual(
            order.vendor_orders.get().status, VendorOrder.Status.EXPIRED
        )
        self.assertEqual(self.stock(self.toy), 5)

    def test_expire_leaves_orders_inside_the_window_alone(self):
        self.add_to_cart(self.customer, self.toy, 2)
        order = checkout(self.customer, SHIPPING)

        expired = expire_overdue_orders()

        order.refresh_from_db()
        self.assertEqual(expired, 0)
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(self.stock(self.toy), 3)

    def test_expire_leaves_paid_orders_alone(self):
        self.add_to_cart(self.customer, self.toy, 2)
        order = checkout(self.customer, SHIPPING)
        Order.objects.filter(pk=order.pk).update(
            status=Order.Status.PAID,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        expired = expire_overdue_orders()

        order.refresh_from_db()
        self.assertEqual(expired, 0)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(self.stock(self.toy), 3)
