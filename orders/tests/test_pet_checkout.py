from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from cart.models import Cart, CartItem
from cart.services import CartOwner, add_to_cart
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import Order, OrderItem
from orders.services import (
    cancel_unpaid_order,
    change_status,
    expire_overdue_orders,
    mark_paid,
)
from pets.models import Pet

PAYLOAD = {
    "shipping_name": "Jane Doe",
    "shipping_phone": "+256700123456",
    "shipping_address": "Plot 1 Main St",
    "shipping_city_district": "Kampala",
    "notes": "Call at the gate",
}


def make_pet(vendor, business, name="Rex", price="500000.00", listing_type="SALE"):
    return Pet.objects.create(
        vendor=vendor,
        business=business,
        listing_type=listing_type,
        name=name,
        age=12,
        gender=Pet.Gender.values[0],
        size=Pet.Size.values[0],
        approved=True,
        price=Decimal(price) if listing_type == "SALE" else None,
    )


class PetCheckoutTests(TestCase):
    def setUp(self):
        self.customer = make_user("petbuyer1", User.Role.CUSTOMER)
        self.other_customer = make_user("petbuyer2", User.Role.CUSTOMER)
        self.vendor_one = make_user("petseller1", User.Role.VENDOR)
        self.vendor_two = make_user("petseller2", User.Role.VENDOR)
        self.business_one = make_business(self.vendor_one, name="Pet Haven")
        self.business_two = make_business(self.vendor_two, name="Fur Shop")
        self.category = make_category()
        self.pet = make_pet(self.vendor_one, self.business_one)
        self.url = reverse("order-checkout")

        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def put_pet_in_cart(self, customer, pet):
        cart, _ = Cart.objects.get_or_create(customer=customer)
        CartItem.objects.create(cart=cart, pet=pet, quantity=1)

    def checkout(self):
        return self.client.post(self.url, PAYLOAD, format="json")

    def status_of(self, pet):
        pet.refresh_from_db()
        return pet.adoption_status

    def test_add_pet_to_cart_is_idempotent(self):
        owner = CartOwner(customer=self.customer)
        _, created = add_to_cart(owner, pet_id=self.pet.pk)
        _, created_again = add_to_cart(owner, pet_id=self.pet.pk)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(CartItem.objects.filter(pet=self.pet).count(), 1)

    def test_adoption_pet_cannot_be_added_to_cart(self):
        adoption_pet = make_pet(
            self.vendor_one, self.business_one, name="Milo", listing_type="ADOPTION"
        )
        with self.assertRaises(ValidationError):
            add_to_cart(CartOwner(customer=self.customer), pet_id=adoption_pet.pk)

    def test_checkout_reserves_the_pet(self):
        self.put_pet_in_cart(self.customer, self.pet)

        response = self.checkout()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.RESERVED)
        order = Order.objects.get(customer=self.customer)
        self.assertEqual(order.total_amount, Decimal("500000.00"))
        item = OrderItem.objects.get(vendor_order__order=order)
        self.assertEqual(item.pet_id, self.pet.pk)
        self.assertIsNone(item.product_id)
        self.assertEqual(item.quantity, 1)
        self.assertFalse(
            Pet.objects.publicly_visible().filter(pk=self.pet.pk).exists()
        )

    def test_second_customer_cannot_buy_a_reserved_pet(self):
        self.put_pet_in_cart(self.customer, self.pet)
        self.put_pet_in_cart(self.other_customer, self.pet)

        first = self.checkout()
        self.assertEqual(first.status_code, 201)

        second_client = APIClient()
        second_client.force_authenticate(self.other_customer)
        second = second_client.post(self.url, PAYLOAD, format="json")

        self.assertEqual(second.status_code, 400)
        self.assertFalse(Order.objects.filter(customer=self.other_customer).exists())
        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.RESERVED)

    def test_expiry_releases_the_pet(self):
        self.put_pet_in_cart(self.customer, self.pet)
        self.checkout()
        order = Order.objects.get(customer=self.customer)
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expire_overdue_orders()

        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.AVAILABLE)

    def test_cancelling_an_unpaid_order_releases_the_pet(self):
        self.put_pet_in_cart(self.customer, self.pet)
        self.checkout()
        order = Order.objects.get(customer=self.customer)

        cancel_unpaid_order(order.pk)

        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.AVAILABLE)

    def test_payment_marks_the_pet_sold_and_clears_the_cart(self):
        self.put_pet_in_cart(self.customer, self.pet)
        self.checkout()
        order = Order.objects.get(customer=self.customer)

        mark_paid(order.pk)

        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.SOLD)
        self.assertFalse(CartItem.objects.filter(pet=self.pet).exists())

    def test_expiry_never_frees_a_sold_pet(self):
        self.put_pet_in_cart(self.customer, self.pet)
        self.checkout()
        order = Order.objects.get(customer=self.customer)
        mark_paid(order.pk)
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expire_overdue_orders()

        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.SOLD)

    def test_mixed_cart_splits_by_vendor_and_takes_stock(self):
        toy = make_product(
            self.business_two, self.category, name="Chew toy", price="10.00", stock=5
        )
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=toy, quantity=2)
        CartItem.objects.create(cart=cart, pet=self.pet, quantity=1)

        response = self.checkout()

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(customer=self.customer)
        self.assertEqual(order.vendor_orders.count(), 2)
        self.assertEqual(order.total_amount, Decimal("500020.00"))
        toy.refresh_from_db()
        self.assertEqual(toy.stock_quantity, 3)
        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.RESERVED)

    def test_vendor_cancelling_a_paid_pet_order_keeps_the_pet_sold(self):
        self.put_pet_in_cart(self.customer, self.pet)
        self.checkout()
        order = Order.objects.get(customer=self.customer)
        mark_paid(order.pk)
        vendor_order = order.vendor_orders.get()

        change_status(vendor_order.pk, "CANCELLED", self.vendor_one)

        # Held until an admin confirms the refund, so it cannot be resold early.
        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.SOLD)
