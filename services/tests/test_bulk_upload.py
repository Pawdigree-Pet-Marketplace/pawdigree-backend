from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business, BusinessCategory
from categories.models import Category
from services.bulk_views import BULK_COLUMNS
from services.models import Service

HEADER = ",".join(BULK_COLUMNS)


def csv_file(*rows, header=HEADER, name="services.csv", encoding="utf-8"):
    content = "\n".join([header, *rows]) + "\n"
    return SimpleUploadedFile(
        name, content.encode(encoding), content_type="text/csv"
    )


def make_vendor(name):
    return User.objects.create_user(
        username=name,
        email=f"{name}@example.com",
        password="test-password-123",
        role=User.Role.VENDOR,
    )


def make_business(vendor, name, business_type, email, **overrides):
    values = {
        "vendor": vendor,
        "name": name,
        "description": "Bulk upload test business",
        "contact": "+256700000001",
        "email": email,
        "address": "Kampala",
        "city_district": "Central",
        "business_type": business_type,
        "verification_status": Business.VerificationStatus.APPROVED,
        "is_active": True,
    }
    values.update(overrides)
    return Business.objects.create(**values)


class BulkTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("service-bulk-upload")

    def row(
        self,
        name="Dog Grooming",
        business_id="",
        category=None,
        price="30000",
        duration="60",
        status_value="",
    ):
        category = category or self.category
        return (
            f"{business_id},{category.pk},{name},Grooming,Bath and trim,"
            f"{price},{duration},{status_value}"
        )

    def upload(self, file):
        return self.client.post(self.url, {"file": file}, format="multipart")


class ServiceBulkUploadTests(BulkTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("svc_bulk_vendor")
        cls.other_vendor = make_vendor("svc_bulk_other")
        cls.customer = User.objects.create_user(
            username="svc_bulk_customer",
            email="svc-bulk-customer@example.com",
            password="test-password-123",
            role=User.Role.CUSTOMER,
        )
        cls.category = Category.objects.create(
            name="Bulk Grooming", kind=Category.Kind.SERVICES
        )
        cls.business = make_business(
            cls.vendor,
            "Bulk Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "bulk-services@example.com",
        )
        cls.other_business = make_business(
            cls.other_vendor,
            "Other Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "other-services@example.com",
        )

    # ---- happy path -------------------------------------------------

    def test_vendor_can_bulk_upload_valid_rows(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(self.row("Dog Grooming"), self.row("Cat Grooming", duration="45"))
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["failed"], [])

        services = Service.objects.filter(business=self.business)
        self.assertEqual(services.count(), 2)
        self.assertEqual(services.get(name="Cat Grooming").duration, 45)

    def test_blank_availability_status_uses_the_default(self):
        self.client.force_authenticate(user=self.vendor)

        self.upload(csv_file(self.row("Default Status")))

        service = Service.objects.get(name="Default Status")
        self.assertEqual(
            service.availability_status, Service.AvailabilityStatus.AVAILABLE
        )

    def test_new_category_is_requested_as_pending(self):
        self.client.force_authenticate(user=self.vendor)

        self.upload(csv_file(self.row("Pending Category")))

        link = BusinessCategory.objects.get(
            business=self.business, category=self.category
        )
        self.assertEqual(
            link.approval_status, BusinessCategory.ApprovalStatus.PENDING
        )

    def test_excel_utf8_bom_file_is_accepted(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(self.row("Excel Item"), encoding="utf-8-sig")
        )

        self.assertEqual(response.data["created"], 1)

    def test_empty_rows_are_skipped(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row("Real Item"), ",,,,,,,"))

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["failed"], [])

    # ---- row errors -------------------------------------------------

    def test_bad_price_fails_but_other_rows_are_created(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(
                self.row("Good One"),
                self.row("Bad Price", price="abc"),
                self.row("Good Two"),
            )
        )

        self.assertEqual(response.data["created"], 2)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertEqual(response.data["failed"][0]["row"], 3)
        self.assertIn("price", response.data["failed"][0]["errors"])
        self.assertFalse(Service.objects.filter(name="Bad Price").exists())

    def test_zero_duration_is_reported(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row("No Time", duration="0")))

        self.assertEqual(response.data["created"], 0)
        self.assertIn("duration", response.data["failed"][0]["errors"])

    def test_cannot_upload_to_another_vendors_business(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(self.row("Stolen", business_id=self.other_business.pk))
        )

        self.assertEqual(response.data["created"], 0)
        self.assertIn("business", response.data["failed"][0]["errors"])
        self.assertFalse(Service.objects.filter(name="Stolen").exists())

    def test_merchandise_category_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)
        merchandise = Category.objects.create(
            name="Toys", kind=Category.Kind.MERCHANDISE
        )

        response = self.upload(csv_file(self.row("Wrong Kind", category=merchandise)))

        self.assertEqual(response.data["created"], 0)
        self.assertIn("category", response.data["failed"][0]["errors"])

    # ---- whole-file errors ------------------------------------------

    def test_missing_required_column_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(
                f",{self.category.pk},No Price Column",
                header="business_id,category_id,name",
            )
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_wrong_file_type_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row(), name="services.txt"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_no_file_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_header_only_file_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_more_than_200_rows_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        rows = [self.row(f"Item {i}") for i in range(201)]
        response = self.upload(csv_file(*rows))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        self.assertEqual(Service.objects.count(), 0)

    # ---- permissions ------------------------------------------------

    def test_anonymous_user_is_rejected(self):
        response = self.upload(csv_file(self.row()))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_is_rejected(self):
        self.client.force_authenticate(user=self.customer)

        response = self.upload(csv_file(self.row()))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Service.objects.count(), 0)


class ServiceBulkBusinessRuleTests(BulkTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("svc_rules_vendor")
        cls.category = Category.objects.create(
            name="Rules Grooming", kind=Category.Kind.SERVICES
        )

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.vendor)

    def assert_row_failed(self, response, field):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertIn(field, response.data["failed"][0]["errors"])
        self.assertEqual(Service.objects.count(), 0)

    def test_default_business_ignores_a_merchandise_business(self):
        services_business = make_business(
            self.vendor,
            "Two Type Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "two-services@example.com",
        )
        make_business(
            self.vendor,
            "Two Type Merch",
            Business.BusinessType.PRODUCT_SELLER,
            "two-merch@example.com",
        )

        response = self.upload(csv_file(self.row("Picks Services")))

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(
            Service.objects.get(name="Picks Services").business,
            services_business,
        )

    def test_two_services_businesses_need_a_business_id(self):
        for number in (1, 2):
            make_business(
                self.vendor,
                f"Services {number}",
                Business.BusinessType.SERVICE_PROVIDER,
                f"services-{number}@example.com",
            )

        response = self.upload(csv_file(self.row("Ambiguous")))

        self.assert_row_failed(response, "business")

    def test_pending_business_cannot_add_services(self):
        business = make_business(
            self.vendor,
            "Pending Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "pending-services@example.com",
            verification_status=Business.VerificationStatus.PENDING,
        )

        response = self.upload(csv_file(self.row(business_id=business.pk)))

        self.assert_row_failed(response, "business")

    def test_inactive_business_cannot_add_services(self):
        business = make_business(
            self.vendor,
            "Inactive Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "inactive-services@example.com",
            is_active=False,
        )

        response = self.upload(csv_file(self.row(business_id=business.pk)))

        self.assert_row_failed(response, "business")

    def test_merchandise_business_cannot_add_services_by_id(self):
        business = make_business(
            self.vendor,
            "Merch Only",
            Business.BusinessType.PRODUCT_SELLER,
            "merch-only@example.com",
        )

        response = self.upload(csv_file(self.row(business_id=business.pk)))

        self.assert_row_failed(response, "business")


class ServiceBulkTemplateTests(TestCase):
    def test_template_is_public_and_matches_the_columns(self):
        response = APIClient().get(reverse("service-bulk-template"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv")
        first_line = response.content.decode().splitlines()[0]
        self.assertEqual(first_line, HEADER)
