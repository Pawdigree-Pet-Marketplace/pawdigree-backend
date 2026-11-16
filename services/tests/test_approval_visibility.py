from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business, BusinessCategory
from categories.models import Category
from services.models import Service


class ServiceApprovalVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        vendor = User.objects.create_user(
            username="visibility_vendor",
            email="visibility@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=vendor,
            name="Visibility Services",
            description="Visibility test",
            contact="+256700000004",
            email="visibility-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.category = Category.objects.create(
            name="Visibility Grooming", kind=Category.Kind.SERVICES
        )
        BusinessCategory.objects.create(
                    kind=Category.Kind.SERVICES,
            business=cls.business,
            category=cls.category,
            approval_status=BusinessCategory.ApprovalStatus.APPROVED,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("service-public-list")

    def make_service(self, name, **overrides):
        values = {
            "business": self.business,
            "category": self.category,
            "name": name,
            "service_type": "Grooming",
            "description": f"{name} service",
            "price": "1000",
            "duration": 30,
        }
        values.update(overrides)
        return Service.objects.create(**values)

    def public_ids(self):
        response = self.client.get(self.url)
        return [item["service_id"] for item in response.data["results"]]

    def test_unapproved_service_is_hidden(self):
        service = self.make_service("Waiting", approved=False)

        self.assertNotIn(service.pk, self.public_ids())

    def test_approved_service_is_visible(self):
        service = self.make_service("Live", approved=True)

        self.assertIn(service.pk, self.public_ids())

    def test_rejected_service_is_hidden(self):
        service = self.make_service(
            "Rejected", approved=False, rejection_reason="Blurry photo"
        )

        self.assertNotIn(service.pk, self.public_ids())

    def test_approved_service_stays_hidden_while_its_category_is_pending(self):
        pending_category = Category.objects.create(
            name="Visibility Training", kind=Category.Kind.SERVICES
        )
        BusinessCategory.objects.create(
                    kind=Category.Kind.SERVICES,
            business=self.business, category=pending_category
        )
        service = self.make_service(
            "Pending category", category=pending_category, approved=True
        )

        self.assertNotIn(service.pk, self.public_ids())

    def test_sending_a_service_back_for_review_hides_it(self):
        service = self.make_service("Edited", approved=True)
        self.assertIn(service.pk, self.public_ids())

        service.send_back_for_review()

        self.assertNotIn(service.pk, self.public_ids())

    def test_public_response_does_not_expose_review_fields(self):
        self.make_service("Fields", approved=True)

        response = self.client.get(self.url)

        item = response.data["results"][0]
        self.assertNotIn("approved", item)
        self.assertNotIn("rejection_reason", item)
        self.assertNotIn("reviewed_at", item)
