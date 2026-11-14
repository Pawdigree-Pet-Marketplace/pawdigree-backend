from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product


class PublicProductListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="public_vendor",
            email="public-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.category = Category.objects.create(name="Pet Toys")
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Approved Shop",
            description="Toys and treats",
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.url = reverse("product-public-list")

    def make_product(self, name="Chew Toy", **extra):
        values = {
            "business": self.business,
            "category": self.category,
            "name": name,
            "price": "15.00",
            "stock_quantity": 5,
        }
        values.update(extra)
        values.setdefault("approved", True)
        return Product.objects.create(**values)

    def test_anyone_can_browse_products(self):
        self.make_product()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(item["name"], "Chew Toy")
        self.assertEqual(item["business_name"], "Approved Shop")
        self.assertEqual(item["category_name"], "Pet Toys")
        self.assertIsNone(item["main_image"])

    def test_inactive_products_are_hidden(self):
        self.make_product(is_active=False)

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 0)

    def test_products_of_unapproved_businesses_are_hidden(self):
        pending = Business.objects.create(
            vendor=self.vendor,
            name="Pending Shop",
            description="Not approved yet",
            verification_status=Business.VerificationStatus.PENDING,
        )
        self.make_product(business=pending)

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 0)

    def test_products_of_inactive_businesses_are_hidden(self):
        Business.objects.filter(pk=self.business.pk).update(is_active=False)
        self.make_product()

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 0)

    def test_availability_follows_stock(self):
        self.make_product(name="In Stock", stock_quantity=3)
        self.make_product(name="Sold Out", stock_quantity=0)

        response = self.client.get(self.url)

        availability = {
            item["name"]: item["is_available"]
            for item in response.data["results"]
        }
        self.assertEqual(
            availability,
            {"In Stock": True, "Sold Out": False},
        )

    def test_admin_only_fields_are_not_exposed(self):
        self.make_product()

        item = self.client.get(self.url).data["results"][0]

        for field in ("is_active", "business", "created_at", "updated_at"):
            self.assertNotIn(field, item)

    def test_results_are_paginated(self):
        for number in range(3):
            self.make_product(name=f"Product {number}")

        response = self.client.get(self.url, {"page_size": 2})

        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
    def test_search_matches_name_and_description(self):
        self.make_product(name="Rope Toy")
        self.make_product(name="Fish Bowl", description="A bowl for a rope fish")
        self.make_product(name="Cat Bed")

        response = self.client.get(self.url, {"search": "rope"})

        names = sorted(item["name"] for item in response.data["results"])
        self.assertEqual(names, ["Fish Bowl", "Rope Toy"])

    def test_filter_by_category(self):
        other = Category.objects.create(name="Pet Food")
        self.make_product(name="Chew Toy")
        self.make_product(name="Dog Biscuits", category=other)

        response = self.client.get(self.url, {"category": other.pk})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Dog Biscuits")

    def test_filter_by_business_name(self):
        other_business = Business.objects.create(
            vendor=self.vendor,
            name="Paws Corner",
            description="Another shop",
            verification_status=Business.VerificationStatus.APPROVED,
        )
        self.make_product(name="Chew Toy")
        self.make_product(name="Leash", business=other_business)

        response = self.client.get(self.url, {"business_name": "paws"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Leash")

    def test_filter_by_price_range(self):
        self.make_product(name="Cheap", price="5.00")
        self.make_product(name="Middle", price="15.00")
        self.make_product(name="Pricey", price="50.00")

        response = self.client.get(
            self.url,
            {"price_min": "10", "price_max": "20"},
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Middle")

    def test_invalid_price_returns_400(self):
        response = self.client.get(self.url, {"price_min": "abc"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price_min", response.data)

    def test_in_stock_filter_hides_sold_out_products(self):
        self.make_product(name="In Stock", stock_quantity=3)
        self.make_product(name="Sold Out", stock_quantity=0)

        response = self.client.get(self.url, {"in_stock": "true"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "In Stock")

    def test_sort_by_price(self):
        self.make_product(name="Middle", price="15.00")
        self.make_product(name="Cheap", price="5.00")
        self.make_product(name="Pricey", price="50.00")

        ascending = self.client.get(self.url, {"sort": "price_asc"})
        descending = self.client.get(self.url, {"sort": "price_desc"})

        self.assertEqual(
            [item["name"] for item in ascending.data["results"]],
            ["Cheap", "Middle", "Pricey"],
        )
        self.assertEqual(
            [item["name"] for item in descending.data["results"]],
            ["Pricey", "Middle", "Cheap"],
        )

    def test_invalid_sort_returns_400(self):
        response = self.client.get(self.url, {"sort": "random"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sort", response.data)

class PublicProductDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="detail_vendor",
            email="detail-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.category = Category.objects.create(name="Pet Beds")
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Detail Shop",
            description="Beds and blankets",
            verification_status=Business.VerificationStatus.APPROVED,
        )

    def make_product(self, **extra):
        values = {
            "business": self.business,
            "category": self.category,
            "name": "Cozy Bed",
            "description": "A soft bed for small dogs",
            "price": "40.00",
            "stock_quantity": 2,
        }
        values.update(extra)
        values.setdefault("approved", True)
        return Product.objects.create(**values)

    def detail_url(self, product):
        return reverse("product-public-detail", kwargs={"pk": product.pk})

    def test_anyone_can_view_a_product(self):
        product = self.make_product()

        response = self.client.get(self.detail_url(product))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Cozy Bed")
        self.assertEqual(response.data["description"], "A soft bed for small dogs")
        self.assertEqual(response.data["business_name"], "Detail Shop")
        self.assertEqual(response.data["category_name"], "Pet Beds")
        self.assertTrue(response.data["is_available"])
        self.assertEqual(response.data["images"], [])

    def test_inactive_product_returns_404(self):
        product = self.make_product(is_active=False)

        response = self.client.get(self.detail_url(product))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_of_unapproved_business_returns_404(self):
        pending = Business.objects.create(
            vendor=self.vendor,
            name="Pending Detail Shop",
            description="Not approved yet",
            verification_status=Business.VerificationStatus.PENDING,
        )
        product = self.make_product(business=pending)

        response = self.client.get(self.detail_url(product))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_in_inactive_category_returns_404(self):
        inactive = Category.objects.create(name="Retired", is_active=False)
        product = self.make_product(category=inactive)

        response = self.client.get(self.detail_url(product))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_only_fields_are_not_exposed(self):
        product = self.make_product()

        data = self.client.get(self.detail_url(product)).data

        for field in ("is_active", "business", "stock_quantity", "created_at"):
            self.assertNotIn(field, data)