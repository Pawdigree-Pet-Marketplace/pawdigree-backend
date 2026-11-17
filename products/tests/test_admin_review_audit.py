from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from cart.tests.helpers import (
    make_business,
    make_category,
    make_product,
    make_user,
)
from products.models import Product

REASON = "The photos do not match the description."


class ProductReviewAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("audit_vendor", User.Role.VENDOR)
        cls.admin = make_user("audit_admin", User.Role.ADMIN)
        cls.business = make_business(cls.vendor)
        cls.category = make_category("Audit Toys")

    def setUp(self):
        self.client = APIClient()
        self.product = make_product(
            self.business, self.category, name="Audit Item"
        )
        self.set_state(approved=False, rejection_reason="")

    def set_state(self, **fields):
        Product.objects.filter(pk=self.product.pk).update(**fields)
        self.product.refresh_from_db()

    def approve_url(self):
        return reverse("product-admin-approve", args=[self.product.pk])

    def reject_url(self):
        return reverse("product-admin-reject", args=[self.product.pk])

    def test_approve_is_recorded(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.approve_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "product.approved")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.actor_role, self.admin.role)
        self.assertEqual(entry.target_type, "products.product")
        self.assertEqual(entry.target_id, str(self.product.pk))
        self.assertEqual(
            entry.details, {"business": str(self.product.business_id)}
        )

    def test_reject_is_recorded_without_the_reason(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.reject_url(), {"reason": REASON}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "product.rejected")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_id, str(self.product.pk))
        self.assertNotIn(REASON, str(entry.details))

    def test_approving_an_approved_product_is_not_recorded(self):
        self.set_state(approved=True)
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.approve_url())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_rejecting_without_a_reason_is_not_recorded(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.reject_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_a_vendor_cannot_approve_and_nothing_is_recorded(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(self.approve_url())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(AuditLog.objects.count(), 0)
