from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from cart.tests.helpers import (
    make_business,
    make_category,
    make_product,
    make_user,
)
from products.models import Product


def words(count):
    return " ".join(["word"] * count)


class ProductDescriptionLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("limit_vendor", User.Role.VENDOR)
        cls.admin = make_user("limit_admin", User.Role.ADMIN)
        cls.business = make_business(cls.vendor)
        cls.category = make_category("Limit Toys")

    def setUp(self):
        self.client = APIClient()
        self.product = make_product(
            self.business, self.category, name="Limit Item"
        )
        Product.objects.filter(pk=self.product.pk).update(approved=True)
        self.product.refresh_from_db()
        self.url = reverse("product-detail", args=[self.product.pk])

    def patch_as(self, user, data):
        self.client.force_authenticate(user=user)
        return self.client.patch(self.url, data, format="json")

    def test_vendor_edit_over_300_words_is_rejected(self):
        before = self.product.description

        response = self.patch_as(self.vendor, {"description": words(301)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("description", response.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.description, before)

    def test_rejected_edit_does_not_send_it_back_for_review(self):
        self.patch_as(self.vendor, {"description": words(301)})

        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)

    def test_vendor_edit_of_exactly_300_words_is_accepted(self):
        response = self.patch_as(self.vendor, {"description": words(300)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.description, words(300))

    def test_editing_another_field_still_works_when_description_is_long(self):
        # Existing long descriptions stay in the database, so a PATCH of a
        # different field must not trip the rule.
        Product.objects.filter(pk=self.product.pk).update(
            description=words(400)
        )

        response = self.patch_as(self.vendor, {"name": "Renamed Item"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
