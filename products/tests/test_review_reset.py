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
from products.models import ProductImage


class ProductReviewResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("reset_vendor", User.Role.VENDOR)
        cls.admin = make_user("reset_admin", User.Role.ADMIN)
        cls.business = make_business(cls.vendor)
        cls.category = make_category("Reset Toys")
        cls.other_category = make_category("Reset Beds")

    def setUp(self):
        self.client = APIClient()
        self.product = make_product(
            self.business, self.category, name="Reset Item"
        )
        self.url = reverse("product-detail", args=[self.product.pk])

    def patch_as(self, user, data):
        self.client.force_authenticate(user=user)
        return self.client.patch(self.url, data, format="json")

    def assert_sent_back(self):
        self.product.refresh_from_db()
        self.assertFalse(self.product.approved)
        self.assertEqual(self.product.rejection_reason, "")
        self.assertIsNone(self.product.reviewed_at)

    def test_vendor_changing_the_name_sends_it_back_for_review(self):
        response = self.patch_as(self.vendor, {"name": "New Name"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_sent_back()

    def test_vendor_changing_the_description_sends_it_back(self):
        self.patch_as(self.vendor, {"description": "Changed text"})

        self.assert_sent_back()

    def test_vendor_changing_the_category_sends_it_back(self):
        response = self.patch_as(
            self.vendor, {"category": self.other_category.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_sent_back()

    def test_vendor_changing_price_keeps_the_approval(self):
        response = self.patch_as(self.vendor, {"price": "99.00"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)

    def test_vendor_changing_stock_keeps_the_approval(self):
        self.patch_as(self.vendor, {"stock_quantity": 50})

        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)
        self.assertEqual(self.product.stock_quantity, 50)

    def test_sending_the_same_name_keeps_the_approval(self):
        self.patch_as(self.vendor, {"name": "Reset Item"})

        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)

    def test_admin_editing_the_name_keeps_the_approval(self):
        response = self.patch_as(self.admin, {"name": "Admin Edit"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)

    def test_editing_a_rejected_product_clears_the_rejection(self):
        self.product.approved = False
        self.product.rejection_reason = "Blurry photo"
        self.product.save()

        self.patch_as(self.vendor, {"name": "Fixed Name"})

        self.assert_sent_back()

    def test_vendor_cannot_approve_their_own_product(self):
        self.product.approved = False
        self.product.save()

        self.patch_as(self.vendor, {"approved": True, "price": "20.00"})

        self.product.refresh_from_db()
        self.assertFalse(self.product.approved)

    def test_vendor_deleting_an_image_sends_it_back(self):
        image = ProductImage.objects.create(
            product=self.product, image="products/reset.png"
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(
            reverse(
                "product-image-delete",
                kwargs={"product_pk": self.product.pk, "pk": image.pk},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assert_sent_back()

    def test_admin_deleting_an_image_keeps_the_approval(self):
        image = ProductImage.objects.create(
            product=self.product, image="products/reset-admin.png"
        )
        self.client.force_authenticate(user=self.admin)

        self.client.delete(
            reverse(
                "product-image-delete",
                kwargs={"product_pk": self.product.pk, "pk": image.pk},
            )
        )

        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)

    def test_vendor_response_shows_the_approval_status(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertTrue(response.data["approved"])
        self.assertIn("rejection_reason", response.data)

    def test_public_detail_does_not_expose_review_fields(self):
        response = APIClient().get(
            reverse("product-public-detail", args=[self.product.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("approved", response.data)
        self.assertNotIn("rejection_reason", response.data)
