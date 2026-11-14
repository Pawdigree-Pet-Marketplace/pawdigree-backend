from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from notification.models import Notification
from services.models import Service
from services.notifications import (
    notify_listing_approved,
    notify_listing_rejected,
)


class ServiceNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="svc_notify_vendor",
            email="svc-notify-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.admin = User.objects.create_user(
            username="svc_notify_admin",
            email="svc-notify-admin@example.com",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Notify Services",
            description="Notify test",
            contact="+256700000006",
            email="notify-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )

    def setUp(self):
        self.service = Service.objects.create(
            business=self.business,
            name="Notify Service",
            service_type="Grooming",
            description="Notify text",
            price="1000",
            duration=30,
        )

    def notifications(self, notification_type):
        return Notification.objects.filter(
            user=self.vendor,
            type=notification_type,
            reference_id=self.service.pk,
        )

    def test_approved_creates_an_in_app_notification(self):
        notify_listing_approved(self.service)

        notification = self.notifications(
            Notification.Type.LISTING_APPROVED
        ).get()
        self.assertIn("Notify Service", notification.message)
        self.assertIn("approved", notification.message)

    def test_approved_emails_the_vendor(self):
        notify_listing_approved(self.service)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.vendor.email])
        self.assertIn("Notify Service", mail.outbox[0].subject)

    def test_rejected_creates_a_notification_with_the_reason(self):
        self.service.rejection_reason = "Blurry photo"

        notify_listing_rejected(self.service)

        notification = self.notifications(
            Notification.Type.LISTING_REJECTED
        ).get()
        self.assertIn("Blurry photo", notification.message)

    def test_rejected_emails_the_vendor_with_the_reason(self):
        self.service.rejection_reason = "Blurry photo"

        notify_listing_rejected(self.service)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.vendor.email])
        self.assertIn("Blurry photo", mail.outbox[0].body)

    def test_email_still_sent_when_the_notification_fails(self):
        with mock.patch(
            "services.notifications.create_notification",
            side_effect=Exception("db down"),
        ):
            notify_listing_approved(self.service)

        self.assertEqual(len(mail.outbox), 1)

    def test_notification_kept_when_the_email_fails(self):
        with mock.patch(
            "services.notifications.send_mail",
            side_effect=Exception("smtp down"),
        ):
            notify_listing_approved(self.service)

        self.assertEqual(
            self.notifications(Notification.Type.LISTING_APPROVED).count(), 1
        )

    def test_approve_endpoint_notifies_and_emails_the_vendor(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            client.post(
                reverse("service-admin-approve", args=[self.service.pk])
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
                reverse("service-admin-reject", args=[self.service.pk]),
                {"reason": "Blurry photo"},
                format="json",
            )

        notification = self.notifications(
            Notification.Type.LISTING_REJECTED
        ).get()
        self.assertIn("Blurry photo", notification.message)
        self.assertEqual(len(mail.outbox), 1)
