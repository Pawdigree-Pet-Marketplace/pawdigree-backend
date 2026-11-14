from unittest import mock

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


class AdminProductReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("review_vendor", User.Role.VENDOR)
        cls.admin = make_user("review_admin", User.Role.ADMIN)
        cls.customer = make_user("review_customer", User.Role.CUSTOMER)
        cls.business = make_business(cls.vendor)
        cls.category = make_category("Review Toys")

    def setUp(self):
        self.client = APIClient()
        self.product = make_product(
            self.business, self.category, name="Review Item"
        )
        self.set_state(approved=False, rejection_reason="")

    def set_state(self, **fields):
        Product.objects.filter(pk=self.product.pk).update(**fields)
        self.product.refresh_from_db()

    def approve_url(self, product=None):
        return reverse("product-admin-approve", args=[(product or self.product).pk])

    def reject_url(self, product=None):
        return reverse("product-admin-reject", args=[(product or self.product).pk])

    def approve_as(self, user):
        self.client.force_authenticate(user=user)
        return self.client.post(self.approve_url())

    def reject_as(self, user, data):
        self.client.force_authenticate(user=user)
        return self.client.post(self.reject_url(), data, format="json")

    # Pending list

    def test_admin_sees_pending_products(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(reverse("product-admin-pending"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.product.pk, ids)

    def test_pending_list_leaves_out_approved_and_rejected(self):
        approved = make_product(self.business, self.category, name="Approved One")
        rejected = make_product(self.business, self.category, name="Rejected One")
        Product.objects.filter(pk=rejected.pk).update(
            approved=False, rejection_reason="Blurry photo"
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(reverse("product-admin-pending"))

        ids = [item["id"] for item in response.data["results"]]
        self.assertNotIn(approved.pk, ids)
        self.assertNotIn(rejected.pk, ids)

    def test_vendor_and_customer_cannot_see_pending_list(self):
        for user in (self.vendor, self.customer):
            self.client.force_authenticate(user=user)

            response = self.client.get(reverse("product-admin-pending"))

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_see_pending_list(self):
        response = APIClient().get(reverse("product-admin-pending"))

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    # Approve

    def test_admin_can_approve_a_product(self):
        response = self.approve_as(self.admin)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)
        self.assertEqual(self.product.rejection_reason, "")
        self.assertEqual(self.product.reviewed_by, self.admin)
        self.assertIsNotNone(self.product.reviewed_at)

    def test_approving_clears_an_earlier_rejection(self):
        self.set_state(rejection_reason="Blurry photo")

        self.approve_as(self.admin)

        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)
        self.assertEqual(self.product.rejection_reason, "")

    def test_approved_product_becomes_public(self):
        public_url = reverse("product-public-detail", args=[self.product.pk])
        self.assertEqual(
            APIClient().get(public_url).status_code, status.HTTP_404_NOT_FOUND
        )

        self.approve_as(self.admin)

        self.assertEqual(
            APIClient().get(public_url).status_code, status.HTTP_200_OK
        )

    def test_cannot_approve_an_already_approved_product(self):
        self.set_state(approved=True)

        response = self.approve_as(self.admin)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_vendor_and_customer_cannot_approve(self):
        for user in (self.vendor, self.customer):
            response = self.approve_as(user)

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.product.refresh_from_db()
        self.assertFalse(self.product.approved)

    def test_approving_an_inactive_product_returns_404(self):
        self.set_state(is_active=False)

        response = self.approve_as(self.admin)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approving_notifies_the_vendor_after_commit(self):
        with (
            mock.patch("products.views.notify_listing_approved") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.approve_as(self.admin)

        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].pk, self.product.pk)

    def test_failed_approval_does_not_notify(self):
        self.set_state(approved=True)

        with (
            mock.patch("products.views.notify_listing_approved") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.approve_as(self.admin)

        notify.assert_not_called()

    # Reject

    def test_admin_can_reject_with_a_reason(self):
        response = self.reject_as(self.admin, {"reason": "Blurry photo"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertFalse(self.product.approved)
        self.assertEqual(self.product.rejection_reason, "Blurry photo")
        self.assertEqual(self.product.reviewed_by, self.admin)
        self.assertIsNotNone(self.product.reviewed_at)

    def test_reject_needs_a_reason(self):
        for data in ({}, {"reason": ""}, {"reason": "   "}):
            response = self.reject_as(self.admin, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.product.refresh_from_db()
        self.assertEqual(self.product.rejection_reason, "")

    def test_cannot_reject_an_already_rejected_product(self):
        self.set_state(rejection_reason="Blurry photo")

        response = self.reject_as(self.admin, {"reason": "Another reason"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.rejection_reason, "Blurry photo")

    def test_admin_can_reject_a_live_product(self):
        self.set_state(approved=True)

        response = self.reject_as(self.admin, {"reason": "Not allowed"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertFalse(self.product.approved)

    def test_rejected_product_is_not_in_the_pending_list(self):
        self.reject_as(self.admin, {"reason": "Blurry photo"})

        response = self.client.get(reverse("product-admin-pending"))

        ids = [item["id"] for item in response.data["results"]]
        self.assertNotIn(self.product.pk, ids)

    def test_vendor_and_customer_cannot_reject(self):
        for user in (self.vendor, self.customer):
            response = self.reject_as(user, {"reason": "Nope"})

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.product.refresh_from_db()
        self.assertEqual(self.product.rejection_reason, "")

    def test_rejecting_notifies_the_vendor_after_commit(self):
        with (
            mock.patch("products.views.notify_listing_rejected") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.reject_as(self.admin, {"reason": "Blurry photo"})

        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].rejection_reason, "Blurry photo")

    def test_invalid_reject_does_not_notify(self):
        with (
            mock.patch("products.views.notify_listing_rejected") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.reject_as(self.admin, {})

        notify.assert_not_called()

    # The review loop

    def test_vendor_edit_after_rejection_puts_it_back_in_the_queue(self):
        self.reject_as(self.admin, {"reason": "Blurry photo"})
        self.client.force_authenticate(user=self.vendor)

        self.client.patch(
            reverse("product-detail", args=[self.product.pk]),
            {"name": "Better Name"},
            format="json",
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("product-admin-pending"))

        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.product.pk, ids)
