from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order, VendorOrder
from orders.services import checkout, mark_paid

SHIPPING = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "",
}


class ExpireOverdueOrdersCommandTests(TestCase):
    def setUp(self):
        self.customer = make_user("buyer1", User.Role.CUSTOMER)
        vendor = make_user("seller1", User.Role.VENDOR)
        business = make_business(vendor, name="Paws Place")
        category = make_category()
        self.toy = make_product(
            business, category, name="Chew toy", price="10.00", stock=5
        )

    def make_order(self):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.toy, quantity=2)
        return checkout(self.customer, SHIPPING)

    def make_overdue(self, order):
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

    def stock(self):
        self.toy.refresh_from_db()
        return self.toy.stock_quantity

    def run_command(self):
        out = StringIO()
        call_command("expire_overdue_orders", stdout=out)
        return out.getvalue()

    def test_overdue_unpaid_order_is_expired_and_stock_returned(self):
        order = self.make_order()
        self.make_overdue(order)
        self.assertEqual(self.stock(), 3)

        self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        for vendor_order in order.vendor_orders.all():
            self.assertEqual(vendor_order.status, VendorOrder.Status.EXPIRED)
        self.assertEqual(self.stock(), 5)

    def test_order_still_inside_its_window_is_left_alone(self):
        order = self.make_order()

        self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(self.stock(), 3)

    def test_paid_order_is_left_alone(self):
        order = self.make_order()
        mark_paid(order.pk)
        self.make_overdue(order)

        self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(self.stock(), 3)

    def test_command_reports_how_many_orders_it_expired(self):
        order = self.make_order()
        self.make_overdue(order)

        self.assertIn("Expired 1 overdue order(s).", self.run_command())

    def test_command_reports_zero_when_nothing_is_overdue(self):
        self.assertIn("Expired 0 overdue order(s).", self.run_command())
