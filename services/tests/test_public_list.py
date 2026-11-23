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
from businesses.models import Business, BusinessCategory
from categories.models import Category
from services.models import Service

TEST_MEDIA_ROOT = tempfile.mkdtemp()
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


def make_image(name):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, STORAGES=TEST_STORAGES)
class PublicServiceListTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.vendor = User.objects.create_user(
            username="public_service_vendor",
            email="public-service-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        self.customer = User.objects.create_user(
            username="public_service_customer",
            email="public-service-customer@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        self.business = self.make_business("Visible Services")
        self.category = Category.objects.create(
            name="Public Grooming",
            kind=Category.Kind.SERVICES,
        )
        self.approve_category(self.business, self.category)
        self.url = reverse("service-public-list")

    def make_business(self, name, **overrides):
        values = {
            "vendor": self.vendor,
            "name": name,
            "description": "Pet care services",
            "contact": "+256700100001",
            "email": f"{name.lower().replace(' ', '-')}@example.com",
            "address": "Kampala Road",
            "city_district": "Kampala",
            "verification_status": Business.VerificationStatus.APPROVED,
        }
        values.update(overrides)
        return Business.objects.create(**values)

    def approve_category(self, business, category, status_value=None):
        return BusinessCategory.objects.create(
            business=business,
            category=category,
            approval_status=(
                status_value or BusinessCategory.ApprovalStatus.APPROVED
            ),
        )

    def make_service(self, name="Dog Grooming", **overrides):
        values = {
            "business": self.business,
            "category": self.category,
            "name": name,
            "service_type": "Grooming",
            "description": f"{name} service",
            "price": "30000.00",
            "duration": 60,
            "approved": True,
        }
        values.update(overrides)
        return Service.objects.create(**values)

    def test_anonymous_and_customer_can_browse_public_services(self):
        self.make_service()

        anonymous_response = self.client.get(self.url)
        self.client.force_authenticate(user=self.customer)
        customer_response = self.client.get(self.url)

        self.assertEqual(anonymous_response.status_code, status.HTTP_200_OK)
        self.assertEqual(customer_response.status_code, status.HTTP_200_OK)
        self.assertEqual(anonymous_response.data["count"], 1)
        self.assertEqual(customer_response.data["count"], 1)

    def test_public_listing_excludes_hidden_service_business_and_category(self):
        visible = self.make_service("Visible")
        self.make_service("Inactive service", is_active=False)
        self.make_business(
            "Inactive Business",
            is_active=False,
        )
        inactive_business = Business.objects.get(name="Inactive Business")
        Service.objects.create(
            business=inactive_business,
            category=self.category,
            approved=True,
            name="Inactive business service",
            service_type="Grooming",
            description="Hidden",
            price="30000.00",
            duration=60,
        )
        pending_business = self.make_business(
            "Pending Business",
            verification_status=Business.VerificationStatus.PENDING,
        )
        self.approve_category(pending_business, self.category)
        Service.objects.create(
            business=pending_business,
            category=self.category,
            approved=True,
            name="Pending business service",
            service_type="Grooming",
            description="Hidden",
            price="30000.00",
            duration=60,
        )
        pending_category = Category.objects.create(
            name="Pending Service Category",
            kind=Category.Kind.SERVICES,
        )
        self.approve_category(
            self.business,
            pending_category,
            BusinessCategory.ApprovalStatus.PENDING,
        )
        self.make_service("Pending category service", category=pending_category)
        inactive_category = Category.objects.create(
            name="Inactive Service Category",
            kind=Category.Kind.SERVICES,
            is_active=False,
        )
        self.approve_category(self.business, inactive_category)
        self.make_service("Inactive category service", category=inactive_category)
        pet_category = Category.objects.create(
            name="Pet-only Category",
            kind=Category.Kind.PETS,
        )
        self.approve_category(self.business, pet_category)
        self.make_service("Wrong category kind service", category=pet_category)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["service_id"] for item in response.data["results"]],
            [visible.pk],
        )

    def test_public_response_contains_customer_fields_only(self):
        self.make_service()

        response = self.client.get(self.url)

        item = response.data["results"][0]
        self.assertEqual(
            set(item),
            {
                "service_id", "name", "service_type", "description", "price",
                "duration", "availability_status", "category_name",
                "business_name", "city_district", "image","review_count","average_rating"
            },
        )
        self.assertEqual(item["category_name"], self.category.name)
        self.assertEqual(item["business_name"], self.business.name)
        self.assertIsNone(item["image"])

    def test_image_uses_service_image_then_business_logo_as_fallback(self):
        image_business = self.make_business(
            "Service Image Business",
            logo=make_image("unused-business-logo.png"),
        )
        self.approve_category(image_business, self.category)
        service_image = self.make_service(
            "Service Image",
            business=image_business,
            image=make_image("service-image.png"),
        )
        logo_business = self.make_business(
            "Logo Fallback Business",
            logo=make_image("business-logo.png"),
        )
        self.approve_category(logo_business, self.category)
        logo_fallback = self.make_service(
            "Logo Fallback",
            business=logo_business,
        )

        response = self.client.get(self.url)

        images = {
            item["name"]: item["image"]
            for item in response.data["results"]
        }
        self.assertTrue(images[service_image.name].endswith(service_image.image.url))
        self.assertTrue(images[logo_fallback.name].endswith(logo_business.logo.url))

    def test_search_matches_name_and_description_case_insensitively(self):
        self.make_service("Cat Bath", description="Gentle coat wash")
        self.make_service("Dog Trim", description="A neat bath for dogs")
        self.make_service("Nail Clipping", description="Paw care")

        by_name = self.client.get(self.url, {"search": "cAt bAtH"})
        by_description = self.client.get(self.url, {"search": "GENTLE COAT"})

        self.assertEqual(by_name.data["count"], 1)
        self.assertEqual(by_name.data["results"][0]["name"], "Cat Bath")
        self.assertEqual(by_description.data["count"], 1)
        self.assertEqual(by_description.data["results"][0]["name"], "Cat Bath")

    def test_category_filter(self):
        other_category = Category.objects.create(
            name="Public Boarding",
            kind=Category.Kind.SERVICES,
        )
        self.approve_category(self.business, other_category)
        self.make_service("Grooming", category=self.category)
        self.make_service("Boarding", category=other_category)

        response = self.client.get(self.url, {"category": other_category.pk})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Boarding")

    def test_location_and_price_filters_can_be_combined(self):
        kampala = self.make_service("Kampala cheap", price="10000.00")
        self.make_service("Kampala costly", price="50000.00")
        entebbe = self.make_business(
            "Entebbe Services",
            city_district="Entebbe",
        )
        self.approve_category(entebbe, self.category)
        self.make_service(
            "Entebbe cheap",
            business=entebbe,
            price="15000.00",
        )

        response = self.client.get(
            self.url,
            {
                "city_district": "kAmPaLa",
                "min_price": "9000",
                "max_price": "20000",
            },
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["service_id"], kampala.pk)

    def test_minimum_and_maximum_price_filters(self):
        self.make_service("Low", price="10000.00")
        self.make_service("Middle", price="30000.00")
        self.make_service("High", price="50000.00")

        response = self.client.get(
            self.url,
            {"min_price": "20000", "max_price": "40000"},
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Middle")

    def test_invalid_category_and_price_values_return_field_errors(self):
        for params, field in (
            ({"category": "not-a-number"}, "category"),
            ({"category": "999999"}, "category"),
            ({"min_price": "abc"}, "min_price"),
            ({"max_price": "-1"}, "max_price"),
            ({"min_price": "40000", "max_price": "10000"}, "min_price"),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertIn(field, response.data)

    def test_page_size_defaults_to_12_and_is_capped_at_50(self):
        for number in range(52):
            self.make_service(f"Page service {number:02d}")

        default_page = self.client.get(self.url)
        large_page = self.client.get(self.url, {"page_size": "100"})
        second_page = self.client.get(
            self.url,
            {"page": "2", "page_size": "1"},
        )

        self.assertEqual(default_page.data["count"], 52)
        self.assertEqual(len(default_page.data["results"]), 12)
        self.assertEqual(len(large_page.data["results"]), 50)
        self.assertEqual(len(second_page.data["results"]), 1)
        self.assertIsNotNone(second_page.data["previous"])


    def test_anonymous_and_customer_can_view_public_service_details(self):
        service = self.make_service()
        detail_url = reverse(
            "service-public-detail",
            kwargs={"pk": service.pk},
        )

        anonymous_response = self.client.get(detail_url)

        self.client.force_authenticate(user=self.customer)
        customer_response = self.client.get(detail_url)

        self.assertEqual(
            anonymous_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            customer_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            anonymous_response.data["service_id"],
            service.pk,
        )
        self.assertEqual(
            anonymous_response.data["name"],
            service.name,
        )
        self.assertEqual(
            anonymous_response.data["business_name"],
            self.business.name,
        )
        self.assertEqual(
            anonymous_response.data["description"],
            service.description,
        )

    def test_public_service_details_returns_404_for_hidden_service(self):
        service = self.make_service(
            "Hidden Service",
            is_active=False,
        )
        detail_url = reverse(
            "service-public-detail",
            kwargs={"pk": service.pk},
        )

        response = self.client.get(detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

