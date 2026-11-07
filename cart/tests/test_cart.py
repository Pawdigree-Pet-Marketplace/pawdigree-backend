from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.db import IntegrityError, transaction
from decimal import Decimal
import uuid

from accounts.models import User
from products.models import Product

from ..models import MAX_LINES_PER_CART, Cart, CartItem
from .helpers import make_business, make_category, make_product, make_user, money
from ..services import product_is_visible, visible_products

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
        
        
class GuestCartModelTests(CartTestCase):
    def test_a_cart_needs_an_owner(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create()

    def test_a_cart_cannot_have_both_owners(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create(customer=self.customer, guest_token=uuid.uuid4())

    def test_many_guest_carts_can_exist(self):
        Cart.objects.create(guest_token=uuid.uuid4())
        Cart.objects.create(guest_token=uuid.uuid4())

        self.assertEqual(Cart.objects.count(), 2)

    def test_two_guest_carts_cannot_share_a_token(self):
        token = uuid.uuid4()
        Cart.objects.create(guest_token=token)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create(guest_token=token)
        
        
#------------------------------------test views --------------------------------

class ViewCartTests(CartTestCase):
    def test_new_customer_gets_an_empty_cart(self):
        response = self.get_cart()

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total_quantity"], 0)
        self.assertEqual(money(data["total"]), Decimal("0.00"))
        self.assertFalse(data["has_unavailable_items"])
        # Reading an empty cart creates nothing.
        self.assertEqual(Cart.objects.count(), 0)

    def test_total_is_the_sum_of_price_times_quantity(self):
        self.add_item(self.product(name="Toy", price="10.00", stock=10), 2)
        self.add_item(self.product(name="Bone", price="3.50", stock=10), 3)

        data = self.get_cart().json()

        totals = [money(line["line_total"]) for line in data["items"]]
        self.assertEqual(totals, [Decimal("20.00"), Decimal("10.50")])
        self.assertEqual(money(data["total"]), Decimal("30.50"))
        self.assertEqual(data["total_quantity"], 5)

    def test_decimal_arithmetic_has_no_rounding_errors(self):
        # With floats, 0.10 * 3 would give 0.30000000000000004.
        self.add_item(self.product(price="0.10", stock=10), 3)
        data = self.get_cart().json()
        self.assertEqual(money(data["total"]), Decimal("0.30"))

    def test_total_follows_the_current_price(self):
        product = self.product(price="10.00", stock=10)
        self.add_item(product, 2)
        self.assertEqual(money(self.get_cart().json()["total"]), Decimal("20.00"))

        product.price = Decimal("12.50")
        product.save()

        data = self.get_cart().json()
        self.assertEqual(money(data["total"]), Decimal("25.00"))
        self.assertEqual(money(data["items"][0]["unit_price"]), Decimal("12.50"))

    def test_line_shows_the_product_details(self):
        product = self.product(name="Chew toy", price="10.00", stock=5)
        item = self.add_item(product, 2)

        line = self.get_cart().json()["items"][0]

        self.assertEqual(line["id"], item.pk)
        self.assertEqual(line["product_id"], product.pk)
        self.assertEqual(line["name"], "Chew toy")
        self.assertEqual(line["business_name"], "Paws Place")
        self.assertEqual(line["quantity"], 2)
        self.assertTrue(line["available"])
        self.assertIsNone(line["issue"])
        self.assertIsNone(line["image"])

    def test_max_quantity_is_stock_capped_at_99(self):
        self.add_item(self.product(name="Few", stock=3), 1)
        self.add_item(self.product(name="Many", stock=500), 1)

        lines = {line["name"]: line for line in self.get_cart().json()["items"]}

        self.assertEqual(lines["Few"]["max_quantity"], 3)
        self.assertEqual(lines["Many"]["max_quantity"], 99)

    def test_unavailable_lines_are_flagged_and_left_out_of_the_total(self):
        self.add_item(self.product(name="Good", price="10.00", stock=5), 2)

        pending_business = make_business(
            self.vendor, name="Pending Shop", approved=False
        )
        inactive_business = make_business(
            self.vendor, name="Closed Shop", active=False
        )
        inactive_category = make_category(name="Retired", active=False)
        unavailable = {
            "Switched off": self.product(name="Switched off", active=False),
            "Empty": self.product(name="Empty", stock=0),
            "Unapproved shop": make_product(
                pending_business, self.category, name="Unapproved shop"
            ),
            "Closed shop": make_product(
                inactive_business, self.category, name="Closed shop"
            ),
            "Retired category": make_product(
                self.business, inactive_category, name="Retired category"
            ),
        }
        for product in unavailable.values():
            self.add_item(product, 1)

        data = self.get_cart().json()

        # Only the good line is counted.
        self.assertEqual(money(data["total"]), Decimal("20.00"))
        self.assertEqual(data["total_quantity"], 2)
        self.assertTrue(data["has_unavailable_items"])

        lines = {line["name"]: line for line in data["items"]}
        self.assertTrue(lines["Good"]["available"])
        for name in unavailable:
            with self.subTest(product=name):
                self.assertFalse(lines[name]["available"])
                self.assertIsNotNone(lines[name]["issue"])
                self.assertEqual(lines[name]["max_quantity"] == 0, name != "Empty" or True)

        self.assertEqual(lines["Empty"]["issue"], "This product is out of stock.")
        self.assertEqual(
            lines["Switched off"]["issue"], "This product is no longer available."
        )

    def test_quantity_above_stock_is_flagged_and_left_out(self):
        # The customer added 5, then stock dropped to 2.
        self.add_item(self.product(price="10.00", stock=2), 5)

        data = self.get_cart().json()

        line = data["items"][0]
        self.assertFalse(line["available"])
        self.assertEqual(line["issue"], "Only 2 left in stock.")
        self.assertEqual(line["max_quantity"], 2)
        self.assertEqual(money(data["total"]), Decimal("0.00"))

    def test_customers_only_see_their_own_cart(self):
        self.add_item(self.product(name="Mine"), 1, customer=self.customer)
        self.add_item(self.product(name="Theirs"), 1, customer=self.other_customer)

        names = [line["name"] for line in self.get_cart().json()["items"]]

        self.assertEqual(names, ["Mine"])

    def test_cart_is_still_there_after_a_refresh(self):
        self.add_item(self.product(price="10.00", stock=10), 2)
        before = self.get_cart().json()

        # A brand new session for the same customer, like a page reload.
        fresh = APIClient()
        fresh.force_authenticate(self.customer)
        after = fresh.get(reverse("cart")).json()

        self.assertEqual(before, after)
        self.assertEqual(len(after["items"]), 1)

    def test_other_roles_are_turned_away(self):
        for user in (self.vendor, self.admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)

                self.assertEqual(self.get_cart().status_code, 403)



class VisibilityRuleTests(CartTestCase):
    def test_the_python_check_matches_the_database_query(self):
        pending_business = make_business(
            self.vendor, name="Pending Shop", approved=False
        )
        inactive_business = make_business(
            self.vendor, name="Closed Shop", active=False
        )
        inactive_category = make_category(name="Retired", active=False)
        products = [
            self.product(name="Visible"),
            self.product(name="Switched off", active=False),
            make_product(pending_business, self.category, name="Unapproved"),
            make_product(inactive_business, self.category, name="Closed"),
            make_product(self.business, inactive_category, name="Retired"),
        ]

        visible_ids = set(visible_products().values_list("pk", flat=True))

        for product in products:
            loaded = Product.objects.select_related("business", "category").get(
                pk=product.pk
            )
            with self.subTest(product=loaded.name):
                self.assertEqual(
                    product_is_visible(loaded), loaded.pk in visible_ids
                )
                
 #-------------------------test guest cart--------------------------------               
class GuestCartTestCase(CartTestCase):
    """A visitor who is not logged in. self.guest is the anonymous client."""

    def setUp(self):
        super().setUp()
        self.guest = APIClient()

    def headers(self, token):
        # This is how the test client spells the X-Cart-Token header.
        return {"HTTP_X_CART_TOKEN": str(token)} if token else {}

    def guest_get(self, token=None):
        return self.guest.get(reverse("cart"), **self.headers(token))

    def guest_add(self, product, quantity=1, token=None):
        return self.guest.post(
            reverse("cart-items"),
            {"product": product.pk, "quantity": quantity},
            format="json",
            **self.headers(token),
        )

    def guest_with(self, *pairs):
        """A guest cart holding (product, quantity) pairs. Returns its token."""
        token = None
        for product, quantity in pairs:
            token = self.guest_add(product, quantity, token=token).json()["cart_token"]
        return token
    
 
class GuestCartTests(GuestCartTestCase):
    def test_guest_sees_an_empty_cart_without_a_token(self):
        response = self.guest_get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertIsNone(response.json()["cart_token"])
        self.assertEqual(Cart.objects.count(), 0)

    def test_first_add_creates_a_guest_cart_and_returns_its_token(self):
        product = self.product(price="10.00", stock=5)

        response = self.guest_add(product, quantity=2)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(money(data["total"]), Decimal("20.00"))
        cart = Cart.objects.get()
        self.assertIsNone(cart.customer)
        self.assertEqual(data["cart_token"], str(cart.guest_token))

    def test_the_token_brings_the_cart_back(self):
        product = self.product(price="10.00", stock=10)
        token = self.guest_add(product, quantity=2).json()["cart_token"]

        data = self.guest_get(token).json()

        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(money(data["total"]), Decimal("20.00"))

    def test_adding_again_with_the_token_uses_the_same_cart(self):
        product = self.product(price="10.00", stock=10)
        token = self.guest_add(product, quantity=2).json()["cart_token"]

        response = self.guest_add(product, quantity=1, token=token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cart.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().quantity, 3)
        self.assertEqual(response.json()["cart_token"], token)

    def test_two_guests_do_not_see_each_others_carts(self):
        first = self.guest_add(self.product(name="A")).json()["cart_token"]
        second = self.guest_add(self.product(name="B")).json()["cart_token"]

        self.assertNotEqual(first, second)
        names = [line["name"] for line in self.guest_get(first).json()["items"]]
        self.assertEqual(names, ["A"])

    def test_unknown_token_shows_an_empty_cart_and_creates_nothing(self):
        response = self.guest_get(uuid.uuid4())

        self.assertEqual(response.json()["items"], [])
        self.assertEqual(Cart.objects.count(), 0)

    def test_unusable_token_is_treated_as_no_token(self):
        response = self.guest.get(reverse("cart"), HTTP_X_CART_TOKEN="not-a-uuid")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_the_server_never_accepts_a_token_chosen_by_the_client(self):
        chosen = uuid.uuid4()

        response = self.guest_add(self.product(), token=chosen)

        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()["cart_token"], str(chosen))
        self.assertFalse(Cart.objects.filter(guest_token=chosen).exists())

    def test_stock_rules_apply_and_a_failed_add_leaves_no_cart(self):
        response = self.guest_add(self.product(stock=2), quantity=3)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Cart.objects.count(), 0)

    def test_hidden_product_cannot_be_added_by_a_guest(self):
        response = self.guest_add(self.product(active=False))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Cart.objects.count(), 0)

    def test_logged_in_customer_ignores_a_guest_token(self):
        token = self.guest_add(self.product(name="Guest item")).json()["cart_token"]
        self.add_item(self.product(name="Mine"), 1)

        response = self.client.get(reverse("cart"), HTTP_X_CART_TOKEN=token)

        names = [line["name"] for line in response.json()["items"]]
        self.assertEqual(names, ["Mine"])

    def test_vendors_and_admins_are_still_turned_away(self):
        product = self.product()
        for user in (self.vendor, self.admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)

                self.assertEqual(self.get_cart().status_code, 403)
                response = self.client.post(
                    reverse("cart-items"), {"product": product.pk}, format="json"
                )
                self.assertEqual(response.status_code, 403)

        self.assertEqual(CartItem.objects.count(), 0)

    def test_a_guest_who_adds_too_fast_is_throttled(self):
        url = reverse("cart-items")

        for _ in range(30):
            response = self.guest.post(url, {"product": 999999}, format="json")
            self.assertEqual(response.status_code, 404)

        response = self.guest.post(url, {"product": 999999}, format="json")
        self.assertEqual(response.status_code, 429)

    def test_logged_in_customers_are_not_throttled_like_guests(self):
        url = reverse("cart-items")

        for _ in range(31):
            response = self.client.post(url, {"product": 999999}, format="json")
            self.assertEqual(response.status_code, 404)



#------------------------------------test merge cart on login-----------------------------------------------
class MergeGuestCartTests(GuestCartTestCase):
    def merge(self, token=None, client=None):
        client = client or self.client
        return client.post(reverse("cart-merge"), **self.headers(token))

    def test_guest_lines_move_into_the_customers_cart(self):
        token = self.guest_with(
            (self.product(name="Toy", price="10.00", stock=10), 2)
        )

        response = self.merge(token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([line["name"] for line in data["items"]], ["Toy"])
        self.assertEqual(money(data["total"]), Decimal("20.00"))
        self.assertFalse(Cart.objects.filter(guest_token=token).exists())
        self.assertEqual(Cart.objects.get().customer, self.customer)

    def test_quantities_for_the_same_product_are_added(self):
        product = self.product(stock=10)
        self.add_item(product, 3)
        token = self.guest_with((product, 2))

        self.merge(token)

        self.assertEqual(CartItem.objects.get().quantity, 5)

    def test_merged_quantity_is_capped_at_the_stock(self):
        product = self.product(stock=4)
        self.add_item(product, 3)
        token = self.guest_with((product, 1))
        product.stock_quantity = 4
        product.save()
        # Give the guest more than fits.
        CartItem.objects.filter(cart__guest_token=token).update(quantity=2)

        self.merge(token)

        self.assertEqual(CartItem.objects.get().quantity, 4)

    def test_merged_quantity_is_capped_at_99(self):
        product = self.product(stock=500)
        self.add_item(product, 90)
        token = self.guest_with((product, 20))

        self.merge(token)

        self.assertEqual(CartItem.objects.get().quantity, 99)

    def test_the_customers_own_quantity_is_never_lowered(self):
        product = self.product(stock=10)
        self.add_item(product, 5)
        token = self.guest_with((product, 1))
        product.stock_quantity = 2
        product.save()

        self.merge(token)

        self.assertEqual(CartItem.objects.get().quantity, 5)

    def test_unavailable_products_are_skipped(self):
        gone = self.product(name="Gone")
        empty = self.product(name="Empty")
        token = self.guest_with((gone, 1), (empty, 1))
        gone.is_active = False
        gone.save()
        empty.stock_quantity = 0
        empty.save()

        self.merge(token)

        self.assertEqual(CartItem.objects.count(), 0)
        self.assertFalse(Cart.objects.filter(guest_token=token).exists())

    def test_merge_respects_the_50_line_limit(self):
        cart = Cart.objects.create(customer=self.customer)
        for number in range(MAX_LINES_PER_CART):
            CartItem.objects.create(
                cart=cart, product=self.product(name=f"Item {number}"), quantity=1
            )
        token = self.guest_with((self.product(name="One too many"), 1))

        self.merge(token)

        self.assertEqual(CartItem.objects.count(), MAX_LINES_PER_CART)
        self.assertFalse(Cart.objects.filter(guest_token=token).exists())

    def test_unknown_token_changes_nothing_and_creates_no_cart(self):
        response = self.merge(uuid.uuid4())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cart.objects.count(), 0)

    def test_no_token_changes_nothing(self):
        response = self.merge()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cart.objects.count(), 0)

    def test_merging_twice_does_nothing_the_second_time(self):
        token = self.guest_with((self.product(stock=10), 2))
        self.merge(token)

        self.assertEqual(self.merge(token).status_code, 200)
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_a_guest_cannot_merge(self):
        response = self.merge(client=self.guest)

        self.assertIn(response.status_code, (401, 403))

    def test_vendors_and_admins_cannot_merge(self):
        for user in (self.vendor, self.admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)

                self.assertEqual(self.merge().status_code, 403)