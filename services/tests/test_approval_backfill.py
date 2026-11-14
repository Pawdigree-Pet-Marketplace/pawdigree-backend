import importlib

from django.apps import apps
from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from services.models import Service

migration = importlib.import_module(
    "services.migrations.0007_approve_existing_services"
)


class ApproveExistingServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        vendor = User.objects.create_user(
            username="service_backfill_vendor",
            email="service-backfill@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=vendor,
            name="Backfill Services",
            description="Backfill test",
            contact="+256700000002",
            email="backfill-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )

    def make_service(self, name, **overrides):
        return Service.objects.create(
            business=self.business,
            name=name,
            service_type="Grooming",
            description="Backfill test service",
            price="1000",
            duration=30,
            **overrides,
        )

    def test_unreviewed_services_become_approved(self):
        service = self.make_service("Old Service")
        self.assertFalse(service.approved)

        migration.approve_existing_services(apps, None)

        service.refresh_from_db()
        self.assertTrue(service.approved)

    def test_rejected_services_stay_unapproved(self):
        service = self.make_service("Rejected", rejection_reason="Bad photo")

        migration.approve_existing_services(apps, None)

        service.refresh_from_db()
        self.assertFalse(service.approved)
