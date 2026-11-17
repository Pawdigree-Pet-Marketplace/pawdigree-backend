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


class ProductBulkCreatedIdsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("bulk_ids_vendor")
        cls.category = Category.objects.create(
            kind=Category.Kind.MERCHANDISE, name="Bulk Ids Supplies"
        )
        cls.business = make_business(
            cls.vendor,
            "Bulk Ids Merchandise",
            Business.BusinessType.PRODUCT_SELLER,
            "bulk-ids@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.vendor)
        self.url = reverse("product-bulk-upload")

    def row(self, name, price="25000"):
        return f",{self.category.pk},{name},Nice item,{price},10"

    def upload(self, *rows):
        return self.client.post(
            self.url, {"file": csv_file(*rows)}, format="multipart"
        )

    def test_response_lists_the_ids_of_the_created_products(self):
        response = self.upload(self.row("First Item"), self.row("Second Item"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(
            sorted(response.data["created_ids"]),
            sorted(
                Product.objects.filter(business=self.business).values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_a_failed_row_adds_no_id(self):
        response = self.upload(
            self.row("Good Item"), self.row("Bad Item", price="not-a-number")
        )

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(len(response.data["created_ids"]), 1)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertEqual(
            response.data["created_ids"],
            [Product.objects.get(name="Good Item").pk],
        )
