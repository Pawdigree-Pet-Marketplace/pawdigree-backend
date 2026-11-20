from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_user
from orders.models import VendorOrder
from orders.services import change_status, checkout, mark_paid, mark_refunded
from orders.tests.test_pet_checkout import PAYLOAD, make_pet
from pets.models import Pet


class PetRefundTests(TestCase):
    def setUp(self):
        self.customer = make_user("petrefundbuyer", User.Role.CUSTOMER)
        self.vendor = make_user("petrefundseller", User.Role.VENDOR)
        self.admin = make_user("petrefundadmin", User.Role.ADMIN)
        self.business = make_business(self.vendor, name="Pet Haven")
        self.pet = make_pet(self.vendor, self.business)

    def status_of(self, pet):
        pet.refresh_from_db()
        return pet.adoption_status

    def cancelled_pet_order(self):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, pet=self.pet, quantity=1)
        order = checkout(self.customer, PAYLOAD)
        mark_paid(order.pk)
        vendor_order = order.vendor_orders.get()
        change_status(vendor_order.pk, VendorOrder.Status.CANCELLED, self.vendor)
        vendor_order.refresh_from_db()
        return vendor_order

    def test_a_cancelled_pet_order_needs_a_refund_of_the_pet_price(self):
        vendor_order = self.cancelled_pet_order()

        self.assertEqual(
            vendor_order.refund_status, VendorOrder.RefundStatus.REQUIRED
        )
        self.assertEqual(vendor_order.refund_amount, Decimal("500000.00"))

    def test_the_pet_stays_sold_until_the_refund_is_confirmed(self):
        self.cancelled_pet_order()

        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.SOLD)

    def test_confirming_the_refund_puts_the_pet_back_on_sale(self):
        vendor_order = self.cancelled_pet_order()

        mark_refunded(vendor_order.pk, self.admin)

        self.assertEqual(self.status_of(self.pet), Pet.AdoptionStatus.AVAILABLE)
