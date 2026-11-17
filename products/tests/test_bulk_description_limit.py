from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from businesses.models import Business
from categories.models import Category
from products.models import Product
from products.tests.test_bulk_upload import (
    csv_file,
    make_business,
    make_vendor,
)


def words(count):
    return " ".join(["word"] * count)


class ProductBulkDescriptionLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("bulk_limit_vendor")
        cls.category = Category.objects.create(
            kind=Category.Kind.MERCHANDISE, name="Bulk Limit Supplies"
        )
        cls.business = make_business(
            cls.vendor,
            "Bulk Limit Merchandise",
            Business.BusinessType.PRODUCT_SELLER,
            "bulk-limit@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.vendor)
        self.url = reverse("product-bulk-upload")

    def row(self, name, description):
        return f",{self.category.pk},{name},{description},25000,10"

    def upload(self, *rows):
        return self.client.post(
            self.url, {"file": csv_file(*rows)}, format="multipart"
        )

    def test_row_over_300_words_fails_and_other_rows_still_upload(self):
        response = self.upload(
            self.row("Short Item", "Nice item"),
            self.row("Long Item", words(301)),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertIn("description", str(response.data["failed"][0]))
        self.assertTrue(Product.objects.filter(name="Short Item").exists())
        self.assertFalse(Product.objects.filter(name="Long Item").exists())

    def test_row_with_exactly_300_words_uploads(self):
        response = self.upload(self.row("Edge Item", words(300)))

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["failed"], [])
