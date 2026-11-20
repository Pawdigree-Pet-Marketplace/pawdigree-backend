from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from bookings.models import Booking
from bookings.tests.helpers import make_service
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order, VendorOrder
from orders.services import checkout, mark_paid
from payments.models import Payment
from pets.models import Pet

SHIPPING = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "Call on arrival",
}

ORDERS_URL = "vendor-transactions-orders"
PET_SALES_URL = "vendor-transactions-pet-sales"
BOOKINGS_URL = "vendor-transactions-bookings"


def make_pet(vendor, business, name="Rex", price="500000.00"):
    return Pet.objects.create(
        vendor=vendor,
        business=business,
        listing_type="SALE",
        name=name,
        age=12,
        gender=Pet.Gender.values[0],
        size=Pet.Size.values[0],
        approved=True,
        price=Decimal(price),
    )


class TransactionTestCase(TestCase):
    def setUp(self):
        self.customer = make_user("txbuyer", User.Role.CUSTOMER)
        self.customer.first_name = "Jamie"
        self.customer.last_name = "Buyer"
        self.customer.phone = "+256700123456"
        self.customer.save()
        self.other_customer = make_user("txbuyer2", User.Role.CUSTOMER)
        self.vendor = make_user("txvendor", User.Role.VENDOR)
        self.other_vendor = make_user("txvendor2", User.Role.VENDOR)

        self.shop = make_business(self.vendor, name="Toy Shop")
        self.food_shop = make_business(self.vendor, name="Food Shop")
        self.pet_shop = make_business(self.vendor, name="Pet Haven")
        self.grooming = make_business(self.vendor, name="Grooming Co")
        self.other_shop = make_business(self.other_vendor, name="Other Shop")

        category = make_category()
        self.toy = make_product(self.shop, category, name="Toy", price="10.00", stock=50)
        self.food = make_product(self.food_shop, category, name="Food", price="20.00", stock=50)
        self.other_toy = make_product(
            self.other_shop, category, name="Other toy", price="5.00", stock=50
        )

        self.client = APIClient()
        self.client.force_authenticate(self.vendor)

    def make_order(self, product=None, pet=None, pay=True, customer=None):
        customer = customer or self.customer
        cart, _ = Cart.objects.get_or_create(customer=customer)
        CartItem.objects.create(cart=cart, product=product, pet=pet, quantity=1)
        order = checkout(customer, SHIPPING)
        if pay:
            mark_paid(order.pk)
        return order

    def vendor_order_id(self, order):
        return order.vendor_orders.get().pk

    def get(self, name, **params):
        return self.client.get(reverse(name), params)

    def ids(self, response, key="id"):
        return [row[key] for row in response.json()["results"]]

    def make_booking(self, service, status="pending", days=5, customer=None):
        start_at = timezone.now() + timedelta(days=days)
        return Booking.objects.create(
            customer=customer or self.customer,
            service=service,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=status,
        )


class AccessTests(TransactionTestCase):
    def test_anonymous_is_rejected(self):
        client = APIClient()
        for name in (ORDERS_URL, PET_SALES_URL, BOOKINGS_URL):
            self.assertEqual(client.get(reverse(name)).status_code, 401)

    def test_customer_is_rejected(self):
        self.client.force_authenticate(self.customer)
        for name in (ORDERS_URL, PET_SALES_URL, BOOKINGS_URL):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)


class OrderTransactionTests(TransactionTestCase):
    def test_lists_only_paid_merchandise(self):
        merch = self.make_order(product=self.toy)
        self.make_order(pet=make_pet(self.vendor, self.pet_shop), customer=self.other_customer)
        self.make_order(product=self.food, pay=False, customer=self.other_customer)
        self.make_booking(make_service(self.grooming))

        response = self.get(ORDERS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(self.ids(response), [self.vendor_order_id(merch)])

    def test_never_shows_another_vendors_orders(self):
        self.make_order(product=self.other_toy)
        self.assertEqual(self.get(ORDERS_URL).json()["count"], 0)

    def test_row_has_customer_name_but_no_email_and_refund_fields(self):
        self.make_order(product=self.toy)
        row = self.get(ORDERS_URL).json()["results"][0]

        self.assertEqual(row["status"], "PAID")
        self.assertEqual(row["status_display"], "Paid")
        self.assertEqual(row["business_id"], str(self.shop.pk))
        self.assertEqual(row["business_name"], "Toy Shop")
        self.assertEqual(row["customer"], {"id": self.customer.pk, "name": "Jamie Buyer"})
        self.assertNotIn("email", row["customer"])
        self.assertEqual(row["shipping_name"], "Jane Doe")
        self.assertEqual(row["refund_status"], "NONE")
        self.assertEqual(row["refund_amount"], "0.00")
        self.assertIn("cancelled_at", row)
        self.assertIn("cancel_reason", row)
        self.assertEqual(row["total"], "10.00")
        self.assertEqual(row["items"][0]["item_type"], "product")
        self.assertIsNone(row["payment"])

    def test_payment_block_hides_amount_and_gateway_details(self):
        order = self.make_order(product=self.toy)
        Payment.objects.create(
            order=order,
            method="pesapal",
            amount=Decimal("999.00"),
            currency="UGX",
            status=Payment.Status.PAID,
            gateway_reference="REF-1",
        )
        payment = self.get(ORDERS_URL).json()["results"][0]["payment"]
        self.assertEqual(
            set(payment), {"method", "status", "reference", "paid_at"}
        )
        self.assertEqual(payment["reference"], "REF-1")

    def test_business_filter_and_main_dashboard_aggregate(self):
        toy_order = self.make_order(product=self.toy)
        food_order = self.make_order(product=self.food)

        everything = self.get(ORDERS_URL)
        self.assertEqual(everything.json()["count"], 2)

        only_toys = self.get(ORDERS_URL, business=str(self.shop.pk))
        self.assertEqual(self.ids(only_toys), [self.vendor_order_id(toy_order)])
        only_food = self.get(ORDERS_URL, business=str(self.food_shop.pk))
        self.assertEqual(self.ids(only_food), [self.vendor_order_id(food_order)])

    def test_business_filter_rejects_foreign_and_malformed_ids(self):
        self.assertEqual(
            self.get(ORDERS_URL, business=str(self.other_shop.pk)).status_code, 404
        )
        self.assertEqual(self.get(ORDERS_URL, business="not-a-uuid").status_code, 400)

    def test_status_filter(self):
        delivered = self.make_order(product=self.toy)
        self.make_order(product=self.food)
        VendorOrder.objects.filter(order=delivered).update(
            status=VendorOrder.Status.DELIVERED
        )

        response = self.get(ORDERS_URL, status="DELIVERED")
        self.assertEqual(self.ids(response), [self.vendor_order_id(delivered)])
        self.assertEqual(self.get(ORDERS_URL, status="bogus").status_code, 400)
        self.assertEqual(self.get(ORDERS_URL, status="RESERVED").status_code, 400)

    def test_pagination(self):
        self.make_order(product=self.toy)
        self.make_order(product=self.toy)
        data = self.get(ORDERS_URL, page_size=1).json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["results"]), 1)
        self.assertIsNotNone(data["next"])


class PetSaleTransactionTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.pet = make_pet(self.vendor, self.pet_shop)

    def test_lists_only_pet_sales(self):
        sale = self.make_order(pet=self.pet)
        self.make_order(product=self.toy)
        self.make_booking(make_service(self.grooming))

        response = self.get(PET_SALES_URL)
        self.assertEqual(self.ids(response), [self.vendor_order_id(sale)])

    def test_paid_sale_row(self):
        self.make_order(pet=self.pet)
        row = self.get(PET_SALES_URL).json()["results"][0]

        self.assertEqual(row["sale_state"], "PAID")
        self.assertIsNone(row["reservation_expires_at"])
        self.assertEqual(row["status"], "PAID")
        self.assertEqual(row["customer"]["name"], "Jamie Buyer")
        self.assertNotIn("email", row["customer"])
        self.assertEqual(row["items"][0]["item_type"], "pet")
        pet = row["items"][0]["pet"]
        self.assertEqual(pet["name"], "Rex")
        self.assertEqual(pet["adoption_status"], "SOLD")
        self.assertIn("refund_status", row)

    def test_reserved_pet_is_shown_with_expiry_and_no_payment(self):
        order = self.make_order(pet=self.pet, pay=False)
        row = self.get(PET_SALES_URL).json()["results"][0]

        self.assertEqual(row["sale_state"], "RESERVED")
        self.assertEqual(row["status"], "PENDING_PAYMENT")
        self.assertIsNone(row["payment"])
        self.assertIsNotNone(row["reservation_expires_at"])
        self.assertEqual(row["items"][0]["pet"]["adoption_status"], "RESERVED")
        order.refresh_from_db()
        self.assertEqual(row["reservation_expires_at"], order.expires_at.isoformat().replace("+00:00", "Z"))

    def test_status_filter_separates_holds_from_paid_sales(self):
        paid_pet = make_pet(self.vendor, self.pet_shop, name="Milo")
        paid = self.make_order(pet=paid_pet)
        held = self.make_order(pet=self.pet, pay=False, customer=self.other_customer)

        both = self.get(PET_SALES_URL)
        self.assertEqual(both.json()["count"], 2)
        reserved = self.get(PET_SALES_URL, status="RESERVED")
        self.assertEqual(self.ids(reserved), [self.vendor_order_id(held)])
        paid_only = self.get(PET_SALES_URL, status="PAID")
        self.assertEqual(self.ids(paid_only), [self.vendor_order_id(paid)])

    def test_expired_hold_is_not_shown(self):
        order = self.make_order(pet=self.pet, pay=False)
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertEqual(self.get(PET_SALES_URL).json()["count"], 0)
        self.assertEqual(self.get(PET_SALES_URL, status="RESERVED").json()["count"], 0)

    def test_cancelled_unpaid_order_is_not_shown(self):
        order = self.make_order(pet=self.pet, pay=False)
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
        VendorOrder.objects.filter(order=order).update(
            status=VendorOrder.Status.CANCELLED
        )
        self.assertEqual(self.get(PET_SALES_URL).json()["count"], 0)

    def test_business_filter_and_scoping(self):
        other_pet = make_pet(self.other_vendor, self.other_shop, name="Other dog")
        self.make_order(pet=self.pet)
        self.make_order(pet=other_pet, customer=self.other_customer)

        self.assertEqual(self.get(PET_SALES_URL).json()["count"], 1)
        mine = self.get(PET_SALES_URL, business=str(self.pet_shop.pk))
        self.assertEqual(mine.json()["count"], 1)
        self.assertEqual(
            self.get(PET_SALES_URL, business=str(self.other_shop.pk)).status_code, 404
        )

    def test_invalid_status_is_rejected(self):
        self.assertEqual(self.get(PET_SALES_URL, status="bogus").status_code, 400)


class BookingTransactionTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.service = make_service(self.grooming, name="Dog Grooming")

    def test_lists_only_bookings_with_customer_name_and_phone(self):
        booking = self.make_booking(self.service)
        self.make_order(product=self.toy)
        self.make_order(pet=make_pet(self.vendor, self.pet_shop), customer=self.other_customer)

        response = self.get(BOOKINGS_URL)
        self.assertEqual(self.ids(response, "booking_id"), [booking.pk])
        row = response.json()["results"][0]
        self.assertEqual(
            row["customer"],
            {"id": self.customer.pk, "name": "Jamie Buyer", "phone": "+256700123456"},
        )
        self.assertEqual(row["service_name"], "Dog Grooming")
        self.assertEqual(row["business_id"], str(self.grooming.pk))
        self.assertEqual(row["business_name"], "Grooming Co")
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["status_display"], "Pending")
        self.assertIn("start_at", row)
        self.assertIn("end_at", row)
        self.assertNotIn("email", row["customer"])

    def test_never_shows_another_vendors_bookings(self):
        other_service = make_service(self.other_shop, name="Cat Sitting")
        self.make_booking(other_service)
        self.assertEqual(self.get(BOOKINGS_URL).json()["count"], 0)

    def test_business_and_status_filters(self):
        second_business = make_business(self.vendor, name="Walking Co")
        walking = make_service(second_business, name="Dog Walking")
        pending = self.make_booking(self.service, days=5)
        accepted = self.make_booking(walking, status="accepted", days=6)

        self.assertEqual(self.get(BOOKINGS_URL).json()["count"], 2)
        only_grooming = self.get(BOOKINGS_URL, business=str(self.grooming.pk))
        self.assertEqual(self.ids(only_grooming, "booking_id"), [pending.pk])
        accepted_only = self.get(BOOKINGS_URL, status="accepted")
        self.assertEqual(self.ids(accepted_only, "booking_id"), [accepted.pk])
        self.assertEqual(self.get(BOOKINGS_URL, status="bogus").status_code, 400)
        self.assertEqual(
            self.get(BOOKINGS_URL, business=str(self.other_shop.pk)).status_code, 404
        )

    def test_pagination(self):
        self.make_booking(self.service, days=5)
        self.make_booking(self.service, days=7)
        data = self.get(BOOKINGS_URL, page_size=1).json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["results"]), 1)
        self.assertIsNotNone(data["next"])


class CustomerNeverShowsEmailTests(TransactionTestCase):
    """A customer with no name and an email-shaped username must not leak it."""

    EMAIL = "leaky@example.com"

    def setUp(self):
        super().setUp()
        self.leaky = make_user("leakybuyer", User.Role.CUSTOMER)
        self.leaky.first_name = ""
        self.leaky.last_name = ""
        self.leaky.username = self.EMAIL
        self.leaky.email = self.EMAIL
        self.leaky.phone = "+256700999999"
        self.leaky.save()
        self.pet = make_pet(self.vendor, self.pet_shop)
        self.service = make_service(self.grooming, name="Dog Grooming")

    def check(self, url):
        response = self.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        row = response.json()["results"][0]
        self.assertEqual(row["customer"]["name"], "Customer")
        self.assertNotIn(self.EMAIL, response.content.decode())

    def test_orders_hide_email_shaped_username(self):
        self.make_order(product=self.toy, customer=self.leaky)
        self.check(ORDERS_URL)

    def test_pet_sales_hide_email_shaped_username(self):
        self.make_order(pet=self.pet, customer=self.leaky)
        self.check(PET_SALES_URL)

    def test_bookings_hide_email_shaped_username(self):
        self.make_booking(self.service, customer=self.leaky)
        self.check(BOOKINGS_URL)
