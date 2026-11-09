from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order

PAYLOAD = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "Call at the gate",
}


class CheckoutApiTests(TestCase):
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
        self.url = reverse("order-checkout")

        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def add_to_cart(self, product, quantity):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)

    def stock(self, product):
        product.refresh_from_db()
        return product.stock_quantity

    def post(self, **changes):
        return self.client.post(self.url, {**PAYLOAD, **changes}, format="json")

    def test_checkout_returns_the_new_order(self):
        self.add_to_cart(self.toy, 2)

        response = self.post()

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "PENDING_PAYMENT")
        self.assertEqual(Decimal(str(data["total_amount"])), Decimal("20.00"))
        self.assertIsNotNone(data["expires_at"])
        self.assertEqual(data["shipping_name"], "Jane Doe")
        self.assertEqual(data["notes"], "Call at the gate")
        self.assertEqual(len(data["vendor_orders"]), 1)
        vendor_order = data["vendor_orders"][0]
        self.assertEqual(vendor_order["business_name"], "Paws Place")
        self.assertEqual(vendor_order["status"], "PENDING_PAYMENT")
        item = vendor_order["items"][0]
        self.assertEqual(item["name"], "Chew toy")
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(Decimal(str(item["unit_price"])), Decimal("10.00"))
        self.assertEqual(Decimal(str(item["subtotal"])), Decimal("20.00"))

    def test_checkout_with_two_vendors_makes_two_vendor_orders(self):
        self.add_to_cart(self.toy, 2)
        self.add_to_cart(self.bed, 1)

        response = self.post()

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["vendor_orders"]), 2)
        self.assertEqual(Decimal(str(data["total_amount"])), Decimal("45.50"))

    def test_checkout_reduces_stock_and_keeps_the_cart(self):
        self.add_to_cart(self.toy, 2)

        self.post()

        self.assertEqual(self.stock(self.toy), 3)
        self.assertEqual(Cart.objects.get(customer=self.customer).items.count(), 1)

    def test_response_does_not_show_stock(self):
        self.add_to_cart(self.toy, 2)

        response = self.post()

        self.assertNotIn("stock", response.content.decode())

    def test_notes_are_optional(self):
        self.add_to_cart(self.toy, 1)
        payload = {key: value for key, value in PAYLOAD.items() if key != "notes"}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["notes"], "")

    def test_phone_is_saved_in_international_format(self):
        self.add_to_cart(self.toy, 1)

        response = self.post(shipping_phone="0700123456")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["shipping_phone"], "+256700123456")

    def test_invalid_phone_is_refused(self):
        self.add_to_cart(self.toy, 1)

        response = self.post(shipping_phone="abc")

        self.assertEqual(response.status_code, 400)
        self.assertIn("shipping_phone", response.json())
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(self.toy), 5)

    def test_missing_details_are_refused(self):
        self.add_to_cart(self.toy, 1)

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, 400)
        for field in (
            "shipping_name",
            "shipping_phone",
            "shipping_address",
            "shipping_city_district",
        ):
            self.assertIn(field, response.json())
        self.assertEqual(Order.objects.count(), 0)

    def test_empty_cart_is_refused(self):
        response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertIn("cart", response.json())
        self.assertEqual(Order.objects.count(), 0)

    def test_out_of_stock_is_refused_and_nothing_changes(self):
        self.add_to_cart(self.toy, 2)
        self.toy.stock_quantity = 0
        self.toy.save()

        response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.json())
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(self.toy), 0)

    def test_login_is_required(self):
        response = APIClient().post(self.url, PAYLOAD, format="json")

        self.assertEqual(response.status_code, 401)

    def test_vendors_cannot_check_out(self):
        client = APIClient()
        client.force_authenticate(self.vendor_one)

        response = client.post(self.url, PAYLOAD, format="json")

        self.assertEqual(response.status_code, 403)
