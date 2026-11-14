import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from services.models import Service

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def make_image(name="groom.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type="image/png",
    )


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ServiceReviewResetTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="service_reset_vendor",
            email="service-reset@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Reset Services",
            description="Reset test",
            contact="+256700000003",
            email="reset-services@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.category = Category.objects.create(
            name="Reset Grooming", kind=Category.Kind.SERVICES
        )
        cls.other_category = Category.objects.create(
            name="Reset Training", kind=Category.Kind.SERVICES
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.vendor)
        self.service = Service.objects.create(
            business=self.business,
            category=self.category,
            name="Reset Service",
            service_type="Grooming",
            description="Original text",
            price="1000",
            duration=30,
            approved=True,
        )
        self.url = reverse("service-detail", args=[self.service.pk])

    def patch(self, data, format="json"):
        return self.client.patch(self.url, data, format=format)

    def assert_sent_back(self):
        self.service.refresh_from_db()
        self.assertFalse(self.service.approved)
        self.assertEqual(self.service.rejection_reason, "")
        self.assertIsNone(self.service.reviewed_by)
        self.assertIsNone(self.service.reviewed_at)

    def assert_still_approved(self):
        self.service.refresh_from_db()
        self.assertTrue(self.service.approved)

    def test_changing_the_name_sends_it_back_for_review(self):
        response = self.patch({"name": "New Name"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_sent_back()

    def test_changing_the_service_type_sends_it_back(self):
        self.patch({"service_type": "Training"})

        self.assert_sent_back()

    def test_changing_the_description_sends_it_back(self):
        self.patch({"description": "Changed text"})

        self.assert_sent_back()

    def test_changing_the_category_sends_it_back(self):
        response = self.patch({"category": self.other_category.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_sent_back()

    def test_adding_an_image_sends_it_back(self):
        response = self.patch({"image": make_image()}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_sent_back()

    def test_removing_an_image_sends_it_back(self):
        Service.objects.filter(pk=self.service.pk).update(
            image="services/existing.png"
        )

        response = self.patch({"image": None})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_sent_back()

    def test_clearing_an_image_that_does_not_exist_keeps_the_approval(self):
        self.patch({"image": None})

        self.assert_still_approved()

    def test_changing_price_keeps_the_approval(self):
        response = self.patch({"price": "99.00"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_still_approved()

    def test_changing_duration_keeps_the_approval(self):
        self.patch({"duration": 45})

        self.assert_still_approved()

    def test_changing_availability_status_keeps_the_approval(self):
        self.patch({"availability_status": "unavailable"})

        self.assert_still_approved()

    def test_sending_the_same_name_keeps_the_approval(self):
        self.patch({"name": "Reset Service"})

        self.assert_still_approved()

    def test_editing_a_rejected_service_clears_the_rejection(self):
        Service.objects.filter(pk=self.service.pk).update(
            approved=False, rejection_reason="Blurry photo"
        )

        self.patch({"name": "Fixed Name"})

        self.assert_sent_back()

    def test_vendor_cannot_approve_their_own_service(self):
        Service.objects.filter(pk=self.service.pk).update(approved=False)

        self.patch({"approved": True, "price": "20.00"})

        self.service.refresh_from_db()
        self.assertFalse(self.service.approved)

    def test_vendor_response_shows_the_approval_status(self):
        response = self.client.get(self.url)

        self.assertTrue(response.data["approved"])
        self.assertIn("rejection_reason", response.data)
        self.assertIn("reviewed_at", response.data)
