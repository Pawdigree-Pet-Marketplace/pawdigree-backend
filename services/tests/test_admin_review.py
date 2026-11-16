from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business, BusinessCategory
from categories.models import Category
from services.models import Service


def make_user(name, role):
    return User.objects.create_user(
        username=name,
        email=f"{name}@example.com",
        password="test-password-123",
        role=role,
    )


class AdminServiceReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("svc_review_vendor", User.Role.VENDOR)
        cls.admin = make_user("svc_review_admin", User.Role.ADMIN)
        cls.customer = make_user("svc_review_customer", User.Role.CUSTOMER)
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Review Services",
            description="Review test",
            contact="+256700000005",
            email="review-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.category = Category.objects.create(
            name="Review Grooming", kind=Category.Kind.SERVICES
        )
        BusinessCategory.objects.create(
                    kind=Category.Kind.SERVICES,
            business=cls.business,
            category=cls.category,
            approval_status=BusinessCategory.ApprovalStatus.APPROVED,
        )

    def setUp(self):
        self.client = APIClient()
        self.service = self.make_service("Review Service")

    def make_service(self, name, **overrides):
        values = {
            "business": self.business,
            "category": self.category,
            "name": name,
            "service_type": "Grooming",
            "description": f"{name} text",
            "price": "1000",
            "duration": 30,
        }
        values.update(overrides)
        return Service.objects.create(**values)

    def set_state(self, **fields):
        Service.objects.filter(pk=self.service.pk).update(**fields)
        self.service.refresh_from_db()

    def approve_url(self):
        return reverse("service-admin-approve", args=[self.service.pk])

    def reject_url(self):
        return reverse("service-admin-reject", args=[self.service.pk])

    def approve_as(self, user):
        self.client.force_authenticate(user=user)
        return self.client.post(self.approve_url())

    def reject_as(self, user, data):
        self.client.force_authenticate(user=user)
        return self.client.post(self.reject_url(), data, format="json")

    def pending_ids(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("service-admin-pending"))
        return [item["service_id"] for item in response.data["results"]]

    # Pending list

    def test_admin_sees_pending_services(self):
        self.assertIn(self.service.pk, self.pending_ids())

    def test_pending_list_leaves_out_approved_and_rejected(self):
        approved = self.make_service("Approved One", approved=True)
        rejected = self.make_service("Rejected One", rejection_reason="Blurry photo")

        ids = self.pending_ids()

        self.assertNotIn(approved.pk, ids)
        self.assertNotIn(rejected.pk, ids)

    def test_vendor_and_customer_cannot_see_pending_list(self):
        for user in (self.vendor, self.customer):
            self.client.force_authenticate(user=user)

            response = self.client.get(reverse("service-admin-pending"))

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_see_pending_list(self):
        response = APIClient().get(reverse("service-admin-pending"))

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    # Approve

    def test_admin_can_approve_a_service(self):
        response = self.approve_as(self.admin)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertTrue(self.service.approved)
        self.assertEqual(self.service.rejection_reason, "")
        self.assertEqual(self.service.reviewed_by, self.admin)
        self.assertIsNotNone(self.service.reviewed_at)

    def test_approving_clears_an_earlier_rejection(self):
        self.set_state(rejection_reason="Blurry photo")

        self.approve_as(self.admin)

        self.service.refresh_from_db()
        self.assertTrue(self.service.approved)
        self.assertEqual(self.service.rejection_reason, "")

    def test_approved_service_becomes_public(self):
        def public_ids():
            response = APIClient().get(reverse("service-public-list"))
            return [item["service_id"] for item in response.data["results"]]

        self.assertNotIn(self.service.pk, public_ids())

        self.approve_as(self.admin)

        self.assertIn(self.service.pk, public_ids())

    def test_cannot_approve_an_already_approved_service(self):
        self.set_state(approved=True)

        response = self.approve_as(self.admin)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_vendor_and_customer_cannot_approve(self):
        for user in (self.vendor, self.customer):
            response = self.approve_as(user)

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.service.refresh_from_db()
        self.assertFalse(self.service.approved)

    def test_approving_an_inactive_service_returns_404(self):
        self.set_state(is_active=False)

        response = self.approve_as(self.admin)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approving_notifies_the_vendor_after_commit(self):
        with (
            mock.patch("services.views.notify_listing_approved") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.approve_as(self.admin)

        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].pk, self.service.pk)

    def test_failed_approval_does_not_notify(self):
        self.set_state(approved=True)

        with (
            mock.patch("services.views.notify_listing_approved") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.approve_as(self.admin)

        notify.assert_not_called()

    # Reject

    def test_admin_can_reject_with_a_reason(self):
        response = self.reject_as(self.admin, {"reason": "Blurry photo"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertFalse(self.service.approved)
        self.assertEqual(self.service.rejection_reason, "Blurry photo")
        self.assertEqual(self.service.reviewed_by, self.admin)
        self.assertIsNotNone(self.service.reviewed_at)

    def test_reject_needs_a_reason(self):
        for data in ({}, {"reason": ""}, {"reason": "   "}):
            response = self.reject_as(self.admin, data)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.service.refresh_from_db()
        self.assertEqual(self.service.rejection_reason, "")

    def test_cannot_reject_an_already_rejected_service(self):
        self.set_state(rejection_reason="Blurry photo")

        response = self.reject_as(self.admin, {"reason": "Another reason"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.service.refresh_from_db()
        self.assertEqual(self.service.rejection_reason, "Blurry photo")

    def test_admin_can_reject_a_live_service(self):
        self.set_state(approved=True)

        response = self.reject_as(self.admin, {"reason": "Not allowed"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertFalse(self.service.approved)

    def test_rejected_service_is_not_in_the_pending_list(self):
        self.reject_as(self.admin, {"reason": "Blurry photo"})

        self.assertNotIn(self.service.pk, self.pending_ids())

    def test_vendor_and_customer_cannot_reject(self):
        for user in (self.vendor, self.customer):
            response = self.reject_as(user, {"reason": "Nope"})

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.service.refresh_from_db()
        self.assertEqual(self.service.rejection_reason, "")

    def test_rejecting_notifies_the_vendor_after_commit(self):
        with (
            mock.patch("services.views.notify_listing_rejected") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.reject_as(self.admin, {"reason": "Blurry photo"})

        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].rejection_reason, "Blurry photo")

    def test_invalid_reject_does_not_notify(self):
        with (
            mock.patch("services.views.notify_listing_rejected") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.reject_as(self.admin, {})

        notify.assert_not_called()

    # The review loop

    def test_vendor_edit_after_rejection_puts_it_back_in_the_queue(self):
        self.reject_as(self.admin, {"reason": "Blurry photo"})
        self.client.force_authenticate(user=self.vendor)

        self.client.patch(
            reverse("service-detail", args=[self.service.pk]),
            {"name": "Better Name"},
            format="json",
        )

        self.assertIn(self.service.pk, self.pending_ids())
