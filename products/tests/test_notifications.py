from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from cart.tests.helpers import (
    make_business,
    make_category,
    make_product,
    make_user,
)
from notification.models import Notification
from products.models import Product
from products.notifications import (
    notify_listing_approved,
    notify_listing_rejected,
)


class ProductNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("notify_vendor", User.Role.VENDOR)
        cls.admin = make_user("notify_admin", User.Role.ADMIN)
        cls.business = make_business(cls.vendor)
        cls.category = make_category("Notify Toys")

    def setUp(self):
        self.product = make_product(
            self.business, self.category, name="Notify Item"
        )

    def notifications(self, notification_type):
        return Notification.objects.filter(
            user=self.vendor,
            type=notification_type,
            reference_id=self.product.pk,
        )

    # Helper functions

    def test_approved_creates_an_in_app_notification(self):
        notify_listing_approved(self.product)

        notification = self.notifications(
            Notification.Type.LISTING_APPROVED
        ).get()
        self.assertIn("Notify Item", notification.message)
        self.assertIn("approved", notification.message)

    def test_approved_emails_the_vendor(self):
        notify_listing_approved(self.product)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.vendor.email])
        self.assertIn("Notify Item", mail.outbox[0].subject)

    def test_rejected_creates_a_notification_with_the_reason(self):
        self.product.rejection_reason = "Blurry photo"

        notify_listing_rejected(self.product)

        notification = self.notifications(
            Notification.Type.LISTING_REJECTED
        ).get()
        self.assertIn("Blurry photo", notification.message)

    def test_rejected_emails_the_vendor_with_the_reason(self):
        self.product.rejection_reason = "Blurry photo"

        notify_listing_rejected(self.product)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.vendor.email])
        self.assertIn("Blurry photo", mail.outbox[0].body)

    def test_email_still_sent_when_the_notification_fails(self):
        with mock.patch(
            "products.notifications.create_notification",
            side_effect=Exception("db down"),
        ):
            notify_listing_approved(self.product)

        self.assertEqual(len(mail.outbox), 1)

    def test_notification_kept_when_the_email_fails(self):
        with mock.patch(
            "products.notifications.send_mail",
            side_effect=Exception("smtp down"),
        ):
            notify_listing_approved(self.product)

        self.assertEqual(
            self.notifications(Notification.Type.LISTING_APPROVED).count(), 1
        )

    # Through the admin endpoints

    def test_approve_endpoint_notifies_and_emails_the_vendor(self):
        Product.objects.filter(pk=self.product.pk).update(approved=False)
        client = APIClient()
        client.force_authenticate(user=self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            client.post(
                reverse("product-admin-approve", args=[self.product.pk])
            )

        self.assertEqual(
            self.notifications(Notification.Type.LISTING_APPROVED).count(), 1
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_reject_endpoint_notifies_and_emails_the_vendor(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            client.post(
                reverse("product-admin-reject", args=[self.product.pk]),
                {"reason": "Blurry photo"},
                format="json",
            )

        notification = self.notifications(
            Notification.Type.LISTING_REJECTED
        ).get()
        self.assertIn("Blurry photo", notification.message)
        self.assertEqual(len(mail.outbox), 1)
