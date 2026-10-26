from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from orders.models import Order, VendorOrder


class OrderModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            username="order_customer",
            email="order_customer@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        cls.vendor = User.objects.create_user(
            username="order_vendor",
            email="order_vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Order Test Business",
            description="Business for order model tests",
            contact="+256700000001",
            email="order_business@example.com",
            address="Kampala",
            city_district="Central",
        )

    def test_order_creation_defaults_and_relationship(self):
        order = Order.objects.create(customer=self.customer)

        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.items_subtotal, 0)
        self.assertEqual(order.total_amount, 0)
        self.assertEqual(str(order), f"Order #{order.pk} - {self.customer}")
        self.assertIsNotNone(order.created_at)
        self.assertIsNotNone(order.updated_at)

    def test_vendor_order_creation_and_relationships(self):
        order = Order.objects.create(customer=self.customer)
        vendor_order = VendorOrder.objects.create(
            order=order,
            business=self.business,
        )

        self.assertEqual(vendor_order.order, order)
        self.assertEqual(vendor_order.business, self.business)
        self.assertEqual(vendor_order.status, VendorOrder.Status.PENDING)
        self.assertEqual(
            str(vendor_order),
            f"Order #{order.pk} - {self.business.name}",
        )
        self.assertEqual(order.vendor_orders.count(), 1)
        self.assertEqual(self.business.vendor_orders.count(), 1)
