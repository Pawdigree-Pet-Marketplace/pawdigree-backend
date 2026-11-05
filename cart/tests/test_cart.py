from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.db import IntegrityError, transaction

from ..models import Cart, CartItem

from accounts.models import User

from ..models import Cart, CartItem
from .helpers import make_business, make_category, make_product, make_user

class CartTestCase(TestCase):
    """Shared setup: people, an approved business and a category."""

    def setUp(self):
        self.customer = make_user("customer1", User.Role.CUSTOMER)
        self.other_customer = make_user("customer2", User.Role.CUSTOMER)
        self.vendor = make_user("vendor1", User.Role.VENDOR)
        self.admin = make_user("admin1", User.Role.ADMIN)
        self.business = make_business(self.vendor)
        self.category = make_category()

        # Requests are made as the first customer unless a test says otherwise.
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def product(self, **kwargs):
        """A visible product with stock, from the approved business."""
        return make_product(self.business, self.category, **kwargs)

    def add_item(self, product, quantity=1, customer=None):
        """Put a line straight into a cart, bypassing the API."""
        cart, _ = Cart.objects.get_or_create(customer=customer or self.customer)
        return CartItem.objects.create(
            cart=cart, product=product, quantity=quantity
        )

    def get_cart(self):
        return self.client.get(reverse("cart"))
    
    
#----------------------test the models-----------------------------------

class CartModelTests(CartTestCase):
    def test_a_customer_cannot_have_two_carts(self):
        Cart.objects.create(customer=self.customer)

        # atomic() keeps the failed insert from breaking the test's transaction.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create(customer=self.customer)

    def test_a_product_can_only_appear_once_per_cart(self):
        cart = Cart.objects.create(customer=self.customer)
        product = self.product()
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=cart, product=product, quantity=1)

    def test_quantity_cannot_be_zero(self):
        cart = Cart.objects.create(customer=self.customer)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=cart, product=self.product(), quantity=0)

    def test_two_customers_can_hold_the_same_product(self):
        product = self.product()
        self.add_item(product, 1, customer=self.customer)
        self.add_item(product, 2, customer=self.other_customer)

        self.assertEqual(CartItem.objects.count(), 2)

    def test_deleting_a_cart_deletes_its_lines(self):
        self.add_item(self.product(), 2)

        Cart.objects.get().delete()

        self.assertEqual(CartItem.objects.count(), 0)