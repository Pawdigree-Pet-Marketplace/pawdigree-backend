from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from services.models import Service


def words(count):
    return " ".join(["word"] * count)


class ServiceDescriptionLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="service_limit_vendor",
            email="service-limit@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Limit Services",
            description="Limit test",
            contact="+256700000004",
            email="limit-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.category = Category.objects.create(
            name="Limit Grooming", kind=Category.Kind.SERVICES
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.vendor)
        self.service = Service.objects.create(
            business=self.business,
            category=self.category,
            name="Limit Service",
            service_type="Grooming",
            description="Original text",
            price="1000",
            duration=30,
            approved=True,
        )
        self.url = reverse("service-detail", args=[self.service.pk])

    def patch(self, data):
        return self.client.patch(self.url, data, format="json")

    def test_edit_over_300_words_is_rejected(self):
        response = self.patch({"description": words(301)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("description", response.data)
        self.service.refresh_from_db()
        self.assertEqual(self.service.description, "Original text")

    def test_rejected_edit_does_not_send_it_back_for_review(self):
        self.patch({"description": words(301)})

        self.service.refresh_from_db()
        self.assertTrue(self.service.approved)

    def test_edit_of_exactly_300_words_is_accepted(self):
        response = self.patch({"description": words(300)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertEqual(self.service.description, words(300))

    def test_editing_another_field_still_works_when_description_is_long(self):
        Service.objects.filter(pk=self.service.pk).update(
            description=words(400)
        )

        response = self.patch({"price": "1500"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
