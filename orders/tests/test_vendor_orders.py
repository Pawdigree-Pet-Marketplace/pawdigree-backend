from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order, VendorOrder
from orders.services import change_status, checkout, mark_paid

SHIPPING = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "Call on arrival",
}


class VendorOrderTestCase(TestCase):
    def setUp(self):
        self.customer = make_user("buyer1", User.Role.CUSTOMER)
        self.vendor_one = make_user("seller1", User.Role.VENDOR)
        self.vendor_two = make_user("seller2", User.Role.VENDOR)
        self.admin = make_user("admin1", User.Role.ADMIN)
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

    def make_unpaid_order(self, customer=None):
        customer = customer or self.customer
        self.add_to_cart(customer, self.toy, 2)
        self.add_to_cart(customer, self.bed, 1)
        return checkout(customer, SHIPPING)

    def make_paid_order(self):
        order = self.make_unpaid_order()
        mark_paid(order.pk)
        return order

    def vendor_order(self, order, business):
        return order.vendor_orders.get(business=business)


class ChangeStatusTests(VendorOrderTestCase):
    def test_vendor_moves_a_paid_order_to_processing(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        result = change_status(
            vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one
        )

        self.assertEqual(result.status, VendorOrder.Status.PROCESSING)
        vendor_order.refresh_from_db()
        self.assertEqual(vendor_order.status, VendorOrder.Status.PROCESSING)

    def test_order_can_go_all_the_way_to_delivered(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        for new_status in (
            VendorOrder.Status.PROCESSING,
            VendorOrder.Status.SHIPPED,
            VendorOrder.Status.DELIVERED,
        ):
            result = change_status(vendor_order.pk, new_status, self.vendor_one)
            self.assertEqual(result.status, new_status)

    def test_changing_one_vendor_order_leaves_the_other_alone(self):
        order = self.make_paid_order()
        mine = self.vendor_order(order, self.business_one)
        other = self.vendor_order(order, self.business_two)

        change_status(mine.pk, VendorOrder.Status.PROCESSING, self.vendor_one)

        other.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(other.status, VendorOrder.Status.PAID)
        self.assertEqual(order.status, Order.Status.PAID)

    def test_a_step_cannot_be_skipped(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        with self.assertRaises(ValidationError):
            change_status(vendor_order.pk, VendorOrder.Status.SHIPPED, self.vendor_one)

        vendor_order.refresh_from_db()
        self.assertEqual(vendor_order.status, VendorOrder.Status.PAID)

    def test_a_delivered_order_cannot_be_changed(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        for new_status in (
            VendorOrder.Status.PROCESSING,
            VendorOrder.Status.SHIPPED,
            VendorOrder.Status.DELIVERED,
        ):
            change_status(vendor_order.pk, new_status, self.vendor_one)

        with self.assertRaises(ValidationError):
            change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor_one)

    def test_a_shipped_order_cannot_be_cancelled(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        change_status(vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one)
        change_status(vendor_order.pk, VendorOrder.Status.SHIPPED, self.vendor_one)

        with self.assertRaises(ValidationError):
            change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor_one)

    def test_payment_statuses_cannot_be_set_by_hand(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        for bad_status in (
            VendorOrder.Status.PAID,
            VendorOrder.Status.PENDING_PAYMENT,
            VendorOrder.Status.EXPIRED,
        ):
            with self.assertRaises(ValidationError):
                change_status(vendor_order.pk, bad_status, self.vendor_one)

    def test_cancelling_gives_back_only_that_vendors_stock(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.assertEqual(self.stock(self.toy), 3)
        self.assertEqual(self.stock(self.bed), 2)

        change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor_one)

        self.assertEqual(self.stock(self.toy), 5)
        self.assertEqual(self.stock(self.bed), 2)

    def test_cancelling_a_processing_order_gives_back_the_stock(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        change_status(vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one)

        change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor_one)

        self.assertEqual(self.stock(self.toy), 5)

    def test_cancelled_order_cannot_be_cancelled_again(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor_one)

        with self.assertRaises(ValidationError):
            change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor_one)

        # The stock was given back once, not twice.
        self.assertEqual(self.stock(self.toy), 5)

    def test_an_unpaid_order_cannot_be_changed(self):
        order = self.make_unpaid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        with self.assertRaises(ValidationError):
            change_status(
                vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one
            )

    def test_a_vendor_cannot_change_another_vendors_order(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        with self.assertRaises(NotFound):
            change_status(
                vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_two
            )

        vendor_order.refresh_from_db()
        self.assertEqual(vendor_order.status, VendorOrder.Status.PAID)

    def test_an_unknown_order_is_not_found(self):
        with self.assertRaises(NotFound):
            change_status(999999, VendorOrder.Status.PROCESSING, self.vendor_one)

    def test_an_admin_can_change_any_order(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        result = change_status(
            vendor_order.pk, VendorOrder.Status.PROCESSING, self.admin
        )

        self.assertEqual(result.status, VendorOrder.Status.PROCESSING)

    def test_a_customer_cannot_change_an_order(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        with self.assertRaises(PermissionDenied):
            change_status(
                vendor_order.pk, VendorOrder.Status.PROCESSING, self.customer
            )


class VendorOrderApiTests(VendorOrderTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.list_url = reverse("vendor-order-list")

    def status_url(self, vendor_order):
        return reverse("vendor-order-status", args=[vendor_order.pk])

    def rows(self, response):
        data = response.data
        return data["results"] if isinstance(data, dict) else data

    def test_vendor_sees_only_their_own_paid_orders(self):
        self.make_paid_order()
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        rows = self.rows(response)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["business_name"], "Paws Place")
        self.assertEqual(len(rows[0]["items"]), 1)
        self.assertEqual(rows[0]["items"][0]["name"], "Chew toy")
        self.assertEqual(rows[0]["total"], "20.00")

    def test_list_includes_the_delivery_details(self):
        self.make_paid_order()
        self.client.force_authenticate(user=self.vendor_one)

        row = self.rows(self.client.get(self.list_url))[0]

        self.assertEqual(row["shipping_name"], "Jane Doe")
        self.assertEqual(row["shipping_phone"], "+256700123456")
        self.assertEqual(row["shipping_address"], "Plot 1 Main St")
        self.assertEqual(row["shipping_city_district"], "Kampala")
        self.assertEqual(row["notes"], "Call on arrival")

    def test_list_does_not_show_unpaid_orders(self):
        self.make_unpaid_order()
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows(response), [])

    def test_list_can_be_filtered_by_status(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        change_status(vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one)
        self.client.force_authenticate(user=self.vendor_one)

        processing = self.client.get(self.list_url, {"status": "PROCESSING"})
        shipped = self.client.get(self.list_url, {"status": "SHIPPED"})

        self.assertEqual(len(self.rows(processing)), 1)
        self.assertEqual(self.rows(shipped), [])

    def test_list_refuses_an_unknown_status_filter(self):
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.get(self.list_url, {"status": "FLYING"})

        self.assertEqual(response.status_code, 400)

    def test_customers_cannot_use_the_vendor_list(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 403)

    def test_anonymous_users_cannot_use_the_vendor_list(self):
        response = self.client.get(self.list_url)

        self.assertIn(response.status_code, (401, 403))

    def test_vendor_changes_the_status_of_their_order(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.patch(
            self.status_url(vendor_order), {"status": "PROCESSING"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "PROCESSING")
        vendor_order.refresh_from_db()
        self.assertEqual(vendor_order.status, VendorOrder.Status.PROCESSING)

    def test_a_refused_move_returns_400(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.patch(
            self.status_url(vendor_order), {"status": "DELIVERED"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data)

    def test_an_unknown_status_value_returns_400(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.patch(
            self.status_url(vendor_order), {"status": "FLYING"}, format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_a_missing_status_returns_400(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.patch(self.status_url(vendor_order), {}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_another_vendors_order_returns_404(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.vendor_two)

        response = self.client.patch(
            self.status_url(vendor_order), {"status": "PROCESSING"}, format="json"
        )

        self.assertEqual(response.status_code, 404)

    def test_customers_cannot_change_a_status(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.customer)

        response = self.client.patch(
            self.status_url(vendor_order), {"status": "PROCESSING"}, format="json"
        )

        self.assertEqual(response.status_code, 403)

    def test_cancelling_through_the_api_gives_back_the_stock(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        self.client.force_authenticate(user=self.vendor_one)

        response = self.client.patch(
            self.status_url(vendor_order), {"status": "CANCELLED"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stock(self.toy), 5)
