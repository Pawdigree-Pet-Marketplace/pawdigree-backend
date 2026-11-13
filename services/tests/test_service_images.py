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
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


def make_image(name="service.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, STORAGES=TEST_STORAGES)
class ServiceImageUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.vendor = User.objects.create_user(
            username="service_image_vendor",
            email="service-image-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.business = Business.objects.create(
            vendor=self.vendor,
            name="Service Image Shop",
            description="Pet services",
            contact="+256700100001",
            email="service-image-shop@example.com",
            address="Kampala Road",
            city_district="Kampala",
        )
        self.category = Category.objects.create(
            name="Image Grooming",
            kind=Category.Kind.SERVICES,
        )
        self.client.force_authenticate(user=self.vendor)
        self.list_url = reverse("service-create")
        self.payload = {
            "business": str(self.business.pk),
            "category": str(self.category.pk),
            "name": "Dog Grooming",
            "service_type": "Grooming",
            "description": "Bath and trim",
            "price": "30000.00",
            "duration": "60",
            "availability_status": "available",
        }

    def test_vendor_can_create_service_with_multipart_image(self):
        response = self.client.post(
            self.list_url,
            {**self.payload, "image": make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        service = Service.objects.get()
        self.assertTrue(service.image.name.startswith("services/"))
        self.assertTrue(response.data["image"].endswith(service.image.url))

    def test_vendor_can_update_service_image_with_multipart(self):
        service = Service.objects.create(
            business=self.business,
            category=self.category,
            name="Dog Grooming",
            service_type="Grooming",
            description="Bath and trim",
            price="30000.00",
            duration=60,
        )

        response = self.client.patch(
            reverse("service-detail", args=[service.pk]),
            {"image": make_image("replacement.png")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        service.refresh_from_db()
        self.assertTrue(service.image.name.startswith("services/"))
        self.assertTrue(response.data["image"].endswith(service.image.url))

    def test_invalid_service_image_is_rejected(self):
        response = self.client.post(
            self.list_url,
            {**self.payload, "image": SimpleUploadedFile(
                "not-an-image.txt", b"not an image", content_type="text/plain"
            )},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)
        self.assertFalse(Service.objects.exists())
