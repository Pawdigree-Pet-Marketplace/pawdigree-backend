from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from adoptions.models import AdoptionApplication
from businesses.models import Business
from pets.models import Pet

User = get_user_model()


class VendorAdoptionApplicationListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="application_vendor",
            email="application-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        cls.another_vendor = User.objects.create_user(
            username="another_application_vendor",
            email="another-application-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        cls.customer = User.objects.create_user(
            username="application_customer",
            email="application-customer@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        cls.admin = User.objects.create_user(
            username="application_admin",
            email="application-admin@example.com",
            password="TestPassword123!",
            role=User.Role.ADMIN,
        )
        cls.system_admin = User.objects.create_user(
            username="application_system_admin",
            email="application-system-admin@example.com",
            password="TestPassword123!",
            role=User.Role.SYSTEM_ADMIN,
        )

        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Application Test Business",
            description="Pet care services",
            contact="+256700123456",
            email="application-business@example.com",
            address="Kampala Road",
            city_district="Kampala",
        )
        cls.another_business = Business.objects.create(
            vendor=cls.another_vendor,
            name="Another Application Business",
            description="Pet services",
            contact="+256700654321",
            email="another-application-business@example.com",
            address="Another Road",
            city_district="Kampala",
        )

        cls.pet = Pet.objects.create(
            vendor=cls.vendor,
            business=cls.business,
            name="Buddy",
            age=6,
            gender=Pet.Gender.MALE,
            size=Pet.Size.MEDIUM,
            approved=True,
        )
        cls.second_pet = Pet.objects.create(
            vendor=cls.vendor,
            business=cls.business,
            name="Luna",
            age=12,
            gender=Pet.Gender.FEMALE,
            size=Pet.Size.SMALL,
            approved=True,
        )
        cls.other_vendor_pet = Pet.objects.create(
            vendor=cls.another_vendor,
            business=cls.another_business,
            name="Other Pet",
            age=4,
            gender=Pet.Gender.MALE,
            size=Pet.Size.MEDIUM,
            approved=True,
        )
        cls.application = AdoptionApplication.objects.create(
            pet=cls.pet,
            customer=cls.customer,
            home_type=AdoptionApplication.HomeType.APARTMENT,
            has_outdoor_space=True,
            has_other_pets=False,
            previous_pet_experience=AdoptionApplication.Experience.NONE,
            message="I have experience caring for pets.",
        )
        cls.second_application = AdoptionApplication.objects.create(
            pet=cls.second_pet,
            customer=cls.customer,
            home_type=AdoptionApplication.HomeType.HOUSE,
            has_outdoor_space=True,
            has_other_pets=True,
            other_pets_details="One cat",
            previous_pet_experience=AdoptionApplication.Experience.SOME,
            message="I have space for another pet.",
        )
        cls.other_vendor_application = AdoptionApplication.objects.create(
            pet=cls.other_vendor_pet,
            customer=cls.customer,
            home_type=AdoptionApplication.HomeType.APARTMENT,
            has_outdoor_space=False,
            has_other_pets=False,
            previous_pet_experience=AdoptionApplication.Experience.NONE,
            message="I would like to adopt this pet.",
        )

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("vendor-adoption-application-list")

    def test_vendor_can_list_own_applications(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(
            {item["application_id"] for item in response.data},
            {
                str(self.application.application_id),
                str(self.second_application.application_id),
            },
        )
        first_result = next(
            item
            for item in response.data
            if item["application_id"] == str(self.application.application_id)
        )
        self.assertEqual(first_result["pet"], self.pet.pk)
        self.assertEqual(first_result["pet_name"], self.pet.name)
        self.assertEqual(first_result["customer_id"], self.customer.pk)
        self.assertEqual(
            first_result["customer_username"], self.customer.username
        )
        self.assertEqual(first_result["customer_email"], self.customer.email)

    def test_vendor_can_filter_applications_by_pet(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url, {"pet_id": self.pet.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["pet"], self.pet.pk)
        self.assertEqual(
            response.data[0]["application_id"],
            str(self.application.application_id),
        )

    def test_vendor_only_sees_own_applications(self):
        self.client.force_authenticate(user=self.another_vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["application_id"],
            str(self.other_vendor_application.application_id),
        )

    def test_customers_cannot_list_vendor_applications(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_can_list_applications_across_vendors(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_system_admin_can_list_applications_across_vendors(self):
        self.client.force_authenticate(user=self.system_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_anonymous_user_cannot_list_vendor_applications(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_invalid_pet_id_returns_400(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url, {"pet_id": "invalid"})

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("pet_id", response.data)
