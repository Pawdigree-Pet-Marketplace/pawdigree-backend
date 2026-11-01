from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from businesses.models import Business
from categories.models import Category
from services.models import Service

User = get_user_model()


class UpdateRemoveServiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = User.objects.create_user(
            username="edit_vendor",
            email="edit-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.another_vendor = User.objects.create_user(
            username="other_edit_vendor",
            email="other-edit-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.customer = User.objects.create_user(
            username="edit_customer",
            email="edit-customer@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        self.admin = User.objects.create_user(
            username="edit_admin",
            email="edit-admin@example.com",
            password="TestPassword123!",
            role=User.Role.ADMIN,
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
        self.service = Service.objects.create(
            business=self.business,
            name="Dog Grooming",
            service_type="Grooming",
            description="Bathing and grooming for dogs.",
            price=Decimal("50000.00"),
            duration=60,
        )
        self.other_service = Service.objects.create(
            business=self.other_business,
            name="Cat Boarding",
            service_type="Boarding",
            description="Overnight cat care.",
            price=Decimal("30000.00"),
            duration=1440,
        )
        self.url = reverse("service-detail", args=[self.service.pk])

    # View

    def test_vendor_can_view_own_service(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Dog Grooming")
        self.assertTrue(response.data["is_active"])

    # Edit

    def test_vendor_can_edit_part_of_a_service(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            self.url,
            {"name": "Full Grooming", "price": "65000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Full Grooming")
        self.assertEqual(self.service.price, Decimal("65000.00"))
        self.assertEqual(self.service.duration, 60)

    def test_vendor_can_replace_a_whole_service(self):
        self.client.force_authenticate(user=self.vendor)
        category = Category.objects.create(name="Grooming")

        response = self.client.put(
            self.url,
            {
                "category": category.pk,
                "name": "Puppy Grooming",
                "service_type": "Grooming",
                "description": "Gentle grooming for puppies.",
                "price": "40000.00",
                "duration": 45,
                "availability_status": "available",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Puppy Grooming")
        self.assertEqual(self.service.duration, 45)

    def test_vendor_can_pause_a_service(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            self.url, {"availability_status": "unavailable"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.refresh_from_db()
        self.assertEqual(self.service.availability_status, "unavailable")
        self.assertTrue(self.service.is_active)

    def test_business_cannot_be_changed_by_an_edit(self):
        self.client.force_authenticate(user=self.vendor)

        self.client.patch(
            self.url, {"business": self.other_business.pk}, format="json"
        )

        self.service.refresh_from_db()
        self.assertEqual(self.service.business, self.business)

    def test_is_active_cannot_be_set_through_an_edit(self):
        self.client.force_authenticate(user=self.vendor)

        self.client.patch(self.url, {"is_active": False}, format="json")

        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)

    def test_negative_price_returns_400(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(self.url, {"price": "-1"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price", response.data)

    def test_zero_duration_returns_400(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(self.url, {"duration": 0}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duration", response.data)

    # Remove

    def test_remove_marks_the_service_inactive_and_keeps_the_row(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)

    def test_removed_service_behaves_as_if_it_does_not_exist(self):
        self.service.is_active = False
        self.service.save()
        self.client.force_authenticate(user=self.vendor)

        for method in (self.client.get, self.client.patch, self.client.delete):
            with self.subTest(method=method.__name__):
                response = method(self.url)
                self.assertEqual(
                    response.status_code, status.HTTP_404_NOT_FOUND
                )

    # Ownership

    def test_vendor_cannot_edit_another_vendors_service(self):
        self.client.force_authenticate(user=self.vendor)
        url = reverse("service-detail", args=[self.other_service.pk])

        response = self.client.patch(url, {"name": "Hijacked"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.other_service.refresh_from_db()
        self.assertEqual(self.other_service.name, "Cat Boarding")

    def test_vendor_cannot_remove_another_vendors_service(self):
        self.client.force_authenticate(user=self.vendor)
        url = reverse("service-detail", args=[self.other_service.pk])

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.other_service.refresh_from_db()
        self.assertTrue(self.other_service.is_active)

    def test_unknown_service_returns_404(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(reverse("service-detail", args=[999999]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Roles

    def test_customers_and_admins_are_forbidden(self):
        for user in (self.customer, self.admin):
            self.client.force_authenticate(user=user)
            for method in (
                self.client.get,
                self.client.patch,
                self.client.delete,
            ):
                with self.subTest(user=user.role, method=method.__name__):
                    response = method(self.url)
                    self.assertEqual(
                        response.status_code, status.HTTP_403_FORBIDDEN
                    )

        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)

    def test_anonymous_user_gets_401(self):
        for method in (self.client.get, self.client.patch, self.client.delete):
            with self.subTest(method=method.__name__):
                response = method(self.url)
                self.assertEqual(
                    response.status_code, status.HTTP_401_UNAUTHORIZED
                )