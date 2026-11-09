from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from accounts.models import User
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order, VendorOrder
from orders.services import (
    cancel_unpaid_order,
    checkout,
    expire_overdue_orders,
    mark_paid,
)

SHIPPING = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "",
}


class MarkPaidTests(TestCase):
    def setUp(self):
        self.customer = make_user("buyer1", User.Role.CUSTOMER)
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

    def add_to_cart(self, product, quantity):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)

    def stock(self, product):
        product.refresh_from_db()
        return product.stock_quantity

    def make_order(self):
        self.add_to_cart(self.toy, 2)
        self.add_to_cart(self.bed, 1)
        return checkout(self.customer, SHIPPING)

    def test_mark_paid_sets_the_order_and_vendor_orders_to_paid(self):
        order = self.make_order()

        result = mark_paid(order.pk)

        order.refresh_from_db()
        self.assertEqual(result.status, Order.Status.PAID)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.vendor_orders.count(), 2)
        for vendor_order in order.vendor_orders.all():
            self.assertEqual(vendor_order.status, VendorOrder.Status.PAID)

    def test_mark_paid_keeps_the_stock_reduced(self):
        order = self.make_order()

        mark_paid(order.pk)

        self.assertEqual(self.stock(self.toy), 3)
        self.assertEqual(self.stock(self.bed), 2)

    def test_mark_paid_removes_the_bought_products_from_the_cart(self):
        order = self.make_order()

        mark_paid(order.pk)

        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 0)

    def test_mark_paid_keeps_products_added_after_checkout(self):
        order = self.make_order()
        other = make_product(
            self.business_one, self.category, name="Leash", price="5.00", stock=4
        )
        self.add_to_cart(other, 1)

        mark_paid(order.pk)

        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual([item.product for item in cart.items.all()], [other])

    def test_mark_paid_twice_is_harmless(self):
        order = self.make_order()

        mark_paid(order.pk)
        result = mark_paid(order.pk)

        self.assertEqual(result.status, Order.Status.PAID)
        self.assertEqual(self.stock(self.toy), 3)

    def test_cancelled_order_cannot_be_paid(self):
        order = self.make_order()
        cancel_unpaid_order(order.pk)

        with self.assertRaises(ValidationError):
            mark_paid(order.pk)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock(self.toy), 5)

    def test_expired_order_cannot_be_paid(self):
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        expire_overdue_orders()

        with self.assertRaises(ValidationError):
            mark_paid(order.pk)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)

    def test_order_past_its_window_but_not_yet_expired_can_still_be_paid(self):
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        result = mark_paid(order.pk)

        self.assertEqual(result.status, Order.Status.PAID)
        self.assertEqual(self.stock(self.toy), 3)

    def test_paid_order_is_not_expired_later(self):
        order = self.make_order()
        mark_paid(order.pk)
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expired = expire_overdue_orders()

        order.refresh_from_db()
        self.assertEqual(expired, 0)
        self.assertEqual(order.status, Order.Status.PAID)

    def test_unknown_order_raises_not_found(self):
        with self.assertRaises(NotFound):
            mark_paid(999999)
