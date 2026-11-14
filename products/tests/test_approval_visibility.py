from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from cart.services import product_is_visible
from cart.tests.helpers import (
    make_business,
    make_category,
    make_product,
    make_user,
)
from products.models import Product


class ProductApprovalVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        vendor = make_user("approval_vendor", User.Role.VENDOR)
        business = make_business(vendor)
        category = make_category()
        cls.approved = make_product(business, category, name="Approved Item")
        cls.pending = make_product(
            business, category, name="Pending Item", approved=False
        )

    def test_queryset_only_returns_approved_products(self):
        visible = Product.objects.publicly_visible()

        self.assertIn(self.approved, visible)
        self.assertNotIn(self.pending, visible)

    def test_single_product_rule_matches_the_queryset(self):
        self.assertTrue(product_is_visible(self.approved))
        self.assertFalse(product_is_visible(self.pending))

    def test_public_list_hides_unapproved_products(self):
        response = APIClient().get(reverse("product-public-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.approved.pk, ids)
        self.assertNotIn(self.pending.pk, ids)

    def test_public_detail_of_unapproved_product_is_404(self):
        response = APIClient().get(
            reverse("product-public-detail", args=[self.pending.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_detail_of_approved_product_works(self):
        response = APIClient().get(
            reverse("product-public-detail", args=[self.approved.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class VendorSeesOwnPendingProductTests(TestCase):
    def test_vendor_list_includes_their_unapproved_product(self):
        vendor = make_user("own_pending_vendor", User.Role.VENDOR)
        business = make_business(vendor)
        category = make_category(name="Own Pending")
        pending = make_product(business, category, name="Mine", approved=False)
        client = APIClient()
        client.force_authenticate(user=vendor)

        response = client.get(reverse("product-list"))

        data = response.data
        results = data["results"] if isinstance(data, dict) else data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(pending.pk, [item["id"] for item in results])
