
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from cart.tests.helpers import make_user
from orders.models import Order


class CustomerOrderListTests(TestCase):
    def setUp(self):
        self.customer = make_user("buyer1", User.Role.CUSTOMER)
        self.other_customer = make_user("buyer2", User.Role.CUSTOMER)
        self.vendor = make_user("seller1", User.Role.VENDOR)

        self.url = reverse("customer-order-list")

        self.client = APIClient()
        self.client.force_authenticate(self.customer)

        self.customer_order = Order.objects.create(
            customer=self.customer,
            total_amount="150.00",
            items_subtotal="150.00",
        )

        self.other_customer_order = Order.objects.create(
            customer=self.other_customer,
            total_amount="250.00",
            items_subtotal="250.00",
        )

    def test_customer_can_view_their_orders(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

        order = response.json()[0]

        self.assertEqual(order["id"], self.customer_order.id)
        self.assertEqual(order["status"], "PENDING_PAYMENT")
        self.assertEqual(order["total_amount"], "150.00")

    def test_customer_cannot_see_another_customers_orders(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        returned_ids = [order["id"] for order in response.json()]

        self.assertIn(self.customer_order.id, returned_ids)
        self.assertNotIn(self.other_customer_order.id, returned_ids)

    def test_customer_with_no_orders_receives_empty_list(self):
        new_customer = make_user("buyer3", User.Role.CUSTOMER)

        client = APIClient()
        client.force_authenticate(new_customer)

        response = client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_login_is_required(self):
        client = APIClient()

        response = client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_vendors_cannot_access_customer_order_history(self):
        client = APIClient()
        client.force_authenticate(self.vendor)

        response = client.get(self.url)

        self.assertEqual(response.status_code, 403)

