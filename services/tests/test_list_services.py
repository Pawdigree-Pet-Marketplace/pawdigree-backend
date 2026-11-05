from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from businesses.models import Business
from services.models import Service

User = get_user_model()


class ListServicesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = User.objects.create_user(
            username="list_vendor",
            email="list-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.another_vendor = User.objects.create_user(
            username="another_list_vendor",
            email="another-list-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.customer = User.objects.create_user(
            username="list_customer",
            email="list-customer@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        self.business_one = self.create_business(
            self.vendor,
            "List Vendor Business One",
            "list-business-one@example.com",
            "+256700100001",
        )
        self.business_two = self.create_business(
            self.vendor,
            "List Vendor Business Two",
            "list-business-two@example.com",
            "+256700100002",
        )
        self.other_business = self.create_business(
            self.another_vendor,
            "Other Vendor Business",
            "other-list-business@example.com",
            "+256700100003",
        )
        self.url = reverse("service-create")

    def create_business(self, vendor, name, email, contact):
        return Business.objects.create(
            vendor=vendor,
            name=name,
            description="Pet care services",
            contact=contact,
            email=email,
            address="Kampala Road",
            city_district="Kampala",
        )

    def create_service(self, business, name, is_active=True):
        return Service.objects.create(
            business=business,
            name=name,
            service_type="Grooming",
            description=f"{name} service description.",
            price="50000.00",
            duration=60,
            is_active=is_active,
        )

    def get_results(self, response):
        if isinstance(response.data, dict) and "results" in response.data:
            return response.data["results"]

        return response.data

    def test_vendor_lists_services_from_all_owned_businesses(self):
        first_service = self.create_service(
            self.business_one,
            "Business One Grooming",
        )
        second_service = self.create_service(
            self.business_two,
            "Business Two Grooming",
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.get_results(response)
        self.assertEqual(
            {item["service_id"] for item in results},
            {first_service.service_id, second_service.service_id},
        )
        self.assertEqual(
            {str(item["business"]) for item in results},
            {str(self.business_one.pk), str(self.business_two.pk)},
        )

    def test_vendor_cannot_see_another_vendors_services(self):
        own_service = self.create_service(self.business_one, "Own Service")
        self.create_service(self.other_business, "Other Vendor Service")
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["service_id"] for item in self.get_results(response)},
            {own_service.service_id},
        )

    def test_inactive_services_are_not_listed(self):
        active_service = self.create_service(
            self.business_one,
            "Active Service",
        )
        self.create_service(
            self.business_two,
            "Inactive Service",
            is_active=False,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["service_id"] for item in self.get_results(response)],
            [active_service.service_id],
        )

    def test_vendor_with_no_services_receives_empty_list(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_results(response), [])

    def test_anonymous_user_cannot_list_services(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_cannot_list_services(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
