from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from businesses.models import Business
from services.models import Service

User = get_user_model()


class CreateServiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = User.objects.create_user(
            username="service_vendor",
            email="service-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.another_vendor = User.objects.create_user(
            username="another_service_vendor",
            email="another-service-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.business = Business.objects.create(
            vendor=self.vendor,
            name="Happy Paws",
            description="Pet care services",
            contact="+256700123456",
            email="happy-paws@example.com",
            address="Kampala Road",
            city_district="Kampala",
        )
        self.other_business = Business.objects.create(
            vendor=self.another_vendor,
            name="Other Pet Care",
            description="Pet services",
            contact="+256700654321",
            email="other@example.com",
            address="Another Road",
            city_district="Kampala",
        )
        self.url = reverse("service-create")
        self.service_data = {
            "business": self.business.pk,
            "name": "Dog Grooming",
            "service_type": "Grooming",
            "description": "Bathing and grooming for dogs.",
            "price": "50000.00",
            "duration": 60,
            "availability_status": "available",
        }

    def create_user(self, username, role):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="TestPassword123!",
            role=role,
        )

    def test_vendor_can_create_service_and_details_are_saved(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url, self.service_data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Service.objects.count(), 1)

        service = Service.objects.get()
        self.assertEqual(service.business, self.business)
        self.assertEqual(service.name, self.service_data["name"])
        self.assertEqual(
            service.service_type,
            self.service_data["service_type"],
        )
        self.assertEqual(
            service.description,
            self.service_data["description"],
        )
        self.assertEqual(service.price, Decimal("50000.00"))
        self.assertEqual(service.duration, self.service_data["duration"])
        self.assertEqual(
            service.availability_status,
            self.service_data["availability_status"],
        )
        self.assertEqual(response.data["name"], service.name)
        self.assertEqual(response.data["service_id"], service.service_id)
        self.assertEqual(response.data["business"], self.business.pk)
        self.assertEqual(response.data["service_type"], service.service_type)
        self.assertEqual(response.data["description"], service.description)
        self.assertEqual(
            Decimal(response.data["price"]),
            Decimal("50000.00"),
        )
        self.assertEqual(response.data["duration"], service.duration)
        self.assertEqual(
            response.data["availability_status"],
            service.availability_status,
        )
        self.assertIn("created_at", response.data)
        self.assertIn("updated_at", response.data)
        self.assertIsNotNone(service.created_at)
        self.assertIsNotNone(service.updated_at)

    def test_anonymous_user_cannot_create_service(self):
        response = self.client.post(
            self.url, self.service_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(Service.objects.count(), 0)

    def test_only_vendors_can_create_services(self):
        for username, role in (
            ("service_customer", User.Role.CUSTOMER),
            ("service_admin", User.Role.ADMIN),
            ("service_system_admin", User.Role.SYSTEM_ADMIN),
        ):
            with self.subTest(role=role):
                user = self.create_user(username, role)
                self.client.force_authenticate(user=user)

                response = self.client.post(
                    self.url, self.service_data, format="json"
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(Service.objects.count(), 0)

    def test_vendor_cannot_use_another_vendors_business(self):
        self.client.force_authenticate(user=self.vendor)
        data = {
            **self.service_data,
            "business": self.other_business.pk,
        }

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Service.objects.count(), 0)

    def test_vendor_cannot_create_service_for_nonexistent_business(self):
        self.client.force_authenticate(user=self.vendor)
        data = {
            **self.service_data,
            "business": 999999,
        }

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Service.objects.count(), 0)

    def test_missing_required_fields_are_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        required_fields = (
            "business",
            "name",
            "service_type",
            "description",
            "price",
            "duration",
        )

        for field in required_fields:
            with self.subTest(field=field):
                data = {
                    **self.service_data,
                    field: "",
                }
                response = self.client.post(
                    self.url, data, format="json"
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertIn(field, response.data)
                self.assertEqual(Service.objects.count(), 0)

    def test_zero_duration_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        data = {**self.service_data, "duration": 0}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("duration", response.data)
        self.assertEqual(Service.objects.count(), 0)

    def test_invalid_price_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        data = {**self.service_data, "price": "not-a-price"}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("price", response.data)
        self.assertEqual(Service.objects.count(), 0)

    def test_negative_duration_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        data = {**self.service_data, "duration": -30}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("duration", response.data)
        self.assertEqual(Service.objects.count(), 0)

    def test_negative_price_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        data = {**self.service_data, "price": "-100.00"}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("price", response.data)
        self.assertEqual(Service.objects.count(), 0)

    def test_price_with_too_many_decimal_places_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        data = {**self.service_data, "price": "100.999"}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("price", response.data)
        self.assertEqual(Service.objects.count(), 0)

    def test_invalid_availability_status_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        data = {
            **self.service_data,
            "availability_status": "sometimes",
        }

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("availability_status", response.data)
        self.assertEqual(Service.objects.count(), 0)
