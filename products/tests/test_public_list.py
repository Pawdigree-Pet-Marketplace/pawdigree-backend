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