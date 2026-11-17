from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from businesses.models import Business
from categories.models import Category
from services.models import Service

REASON = "The description does not match the service."


def make_user(name, role):
    return User.objects.create_user(
        username=name,
        email=f"{name}@example.com",
        password="test-password-123",
        role=role,
    )


class ServiceReviewAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_user("svc_audit_vendor", User.Role.VENDOR)
        cls.admin = make_user("svc_audit_admin", User.Role.ADMIN)
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Audit Services",
            description="Audit test",
            contact="+256700000006",
            email="audit-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.category = Category.objects.create(
            name="Audit Grooming", kind=Category.Kind.SERVICES
        )

    def setUp(self):
        self.client = APIClient()
        self.service = Service.objects.create(
            business=self.business,
            category=self.category,
            name="Audit Service",
            service_type="Grooming",
            description="Audit text",
            price="1000",
            duration=30,
            approved=False,
        )

    def set_state(self, **fields):
        Service.objects.filter(pk=self.service.pk).update(**fields)
        self.service.refresh_from_db()

    def approve_url(self):
        return reverse("service-admin-approve", args=[self.service.pk])

    def reject_url(self):
        return reverse("service-admin-reject", args=[self.service.pk])

    def test_approve_is_recorded(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.approve_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "service.approved")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.actor_role, self.admin.role)
        self.assertEqual(entry.target_type, "services.service")
        self.assertEqual(entry.target_id, str(self.service.pk))
        self.assertEqual(
            entry.details, {"business": str(self.service.business_id)}
        )

    def test_reject_is_recorded_without_the_reason(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.reject_url(), {"reason": REASON}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "service.rejected")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_id, str(self.service.pk))
        self.assertNotIn(REASON, str(entry.details))

    def test_approving_an_approved_service_is_not_recorded(self):
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
