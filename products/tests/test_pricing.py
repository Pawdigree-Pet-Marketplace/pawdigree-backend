from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product
from products.pricing import calculate_cart_total


class CartTotalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="total_vendor",
            email="total-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.category = Category.objects.create(kind=Category.Kind.MERCHANDISE, name="Pet Food")
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Total Shop",
            description="Food and toys",
            verification_status=Business.VerificationStatus.APPROVED,
        )

    def make_product(self, name="Dog Food", price="10.00", **extra):
        values = {
            "business": self.business,
            "category": self.category,
            "name": name,
            "price": Decimal(price),
            "stock_quantity": 10,
        }
        values.update(extra)
        return Product.objects.create(**values)

    def test_empty_cart_totals_zero(self):
        result = calculate_cart_total([])

        self.assertEqual(result["total"], Decimal("0.00"))
        self.assertEqual(result["lines"], [])

    def test_total_adds_up_several_items(self):
        food = self.make_product(name="Dog Food", price="10.50")
        toy = self.make_product(name="Chew Toy", price="4.25")

        result = calculate_cart_total([(food, 2), (toy, 3)])

        self.assertEqual(result["lines"][0]["line_total"], Decimal("21.00"))
        self.assertEqual(result["lines"][1]["line_total"], Decimal("12.75"))
        self.assertEqual(result["total"], Decimal("33.75"))

    def test_price_change_after_adding_is_reflected(self):
        product = self.make_product(price="10.00")
        before = calculate_cart_total([(product, 2)])

        Product.objects.filter(pk=product.pk).update(price=Decimal("12.50"))
        product.refresh_from_db()
        after = calculate_cart_total([(product, 2)])

        self.assertEqual(before["total"], Decimal("20.00"))
        self.assertEqual(after["total"], Decimal("25.00"))

    def test_inactive_product_is_flagged_and_excluded(self):
        good = self.make_product(name="Good", price="5.00")
        gone = self.make_product(name="Gone", price="9.00", is_active=False)

        result = calculate_cart_total([(good, 1), (gone, 1)])

        self.assertEqual(result["total"], Decimal("5.00"))
        self.assertFalse(result["lines"][1]["available"])
        self.assertEqual(
            result["lines"][1]["unavailable_reason"], "not_available"
        )

    def test_out_of_stock_product_is_flagged_and_excluded(self):
        product = self.make_product(stock_quantity=0)

        result = calculate_cart_total([(product, 1)])

        self.assertEqual(result["total"], Decimal("0.00"))
        self.assertEqual(
            result["lines"][0]["unavailable_reason"], "out_of_stock"
        )

    def test_quantity_above_stock_is_flagged_and_excluded(self):
        product = self.make_product(stock_quantity=2)

        result = calculate_cart_total([(product, 3)])

        self.assertEqual(result["total"], Decimal("0.00"))
        self.assertEqual(
            result["lines"][0]["unavailable_reason"], "insufficient_stock"
        )

    def test_product_of_unapproved_business_is_excluded(self):
        pending = Business.objects.create(
            vendor=self.vendor,
            name="Pending Shop",
            description="Not approved yet",
            verification_status=Business.VerificationStatus.PENDING,
        )
        product = self.make_product(business=pending)

        result = calculate_cart_total([(product, 1)])

        self.assertEqual(result["total"], Decimal("0.00"))
        self.assertFalse(result["lines"][0]["available"])

    def test_line_totals_always_add_up_to_total(self):
        ok = self.make_product(name="Ok", price="3.33")
        sold_out = self.make_product(name="Sold Out", stock_quantity=0)

        result = calculate_cart_total([(ok, 3), (sold_out, 2)])

        self.assertEqual(
            sum(line["line_total"] for line in result["lines"]),
            result["total"],
        )

    def test_invalid_quantity_is_rejected(self):
        product = self.make_product()

        for bad in (0, -1, 1.5, "2", None):
            with self.subTest(quantity=bad), self.assertRaises(ValueError):
                calculate_cart_total([(product, bad)])