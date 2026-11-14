from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product
from products.views import BULK_COLUMNS

HEADER = ",".join(BULK_COLUMNS)


def csv_file(*rows, header=HEADER, name="products.csv", encoding="utf-8"):
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


class ProductBulkUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("bulk_vendor")
        cls.other_vendor = make_vendor("bulk_other_vendor")
        cls.customer = User.objects.create_user(
            username="bulk_customer",
            email="bulk-customer@example.com",
            password="test-password-123",
            role=User.Role.CUSTOMER,
        )
        cls.category = Category.objects.create(name="Bulk Supplies")
        cls.business = make_business(
            cls.vendor,
            "Bulk Merchandise",
            Business.BusinessType.PRODUCT_SELLER,
            "bulk-merch@example.com",
        )
        cls.other_business = make_business(
            cls.other_vendor,
            "Other Merchandise",
            Business.BusinessType.PRODUCT_SELLER,
            "other-merch@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("product-bulk-upload")

    def row(self, name="Dog Leash", business_id="", price="25000", stock="40"):
        return f"{business_id},{self.category.pk},{name},Nice item,{price},{stock}"

    def upload(self, file):
        return self.client.post(self.url, {"file": file}, format="multipart")

    # ---- happy path -------------------------------------------------

    def test_vendor_can_bulk_upload_valid_rows(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(self.row("Dog Leash"), self.row("Cat Post", stock="15"))
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["failed"], [])

        products = Product.objects.filter(business=self.business)
        self.assertEqual(products.count(), 2)
        self.assertEqual(products.get(name="Dog Leash").stock_quantity, 40)
        self.assertEqual(products.get(name="Cat Post").stock_quantity, 15)

    def test_blank_stock_uses_the_model_default(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row("No Stock", stock="")))

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(Product.objects.get(name="No Stock").stock_quantity, 0)

    def test_excel_utf8_bom_file_is_accepted(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row("Excel Item"), encoding="utf-8-sig"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 1)

    def test_empty_rows_are_skipped(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row("Real Item"), ",,,,,"))

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

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertEqual(response.data["failed"][0]["row"], 3)
        self.assertIn("price", response.data["failed"][0]["errors"])
        self.assertFalse(Product.objects.filter(name="Bad Price").exists())

    def test_cannot_upload_to_another_vendors_business(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(self.row("Stolen", business_id=self.other_business.pk))
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertIn("business", response.data["failed"][0]["errors"])
        self.assertFalse(Product.objects.filter(name="Stolen").exists())

    # ---- default business -------------------------------------------

    def test_default_business_ignores_a_services_business(self):
        vendor = make_vendor("two_business_vendor")
        merch = make_business(
            vendor,
            "Two Type Merch",
            Business.BusinessType.PRODUCT_SELLER,
            "two-merch@example.com",
        )
        make_business(
            vendor,
            "Two Type Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "two-services@example.com",
        )
        self.client.force_authenticate(user=vendor)

        response = self.upload(csv_file(self.row("Picks Merch")))

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(Product.objects.get(name="Picks Merch").business, merch)

    def test_two_merchandise_businesses_need_a_business_id(self):
        vendor = make_vendor("many_merch_vendor")
        make_business(
            vendor, "Merch One", Business.BusinessType.PRODUCT_SELLER,
            "merch-one@example.com",
        )
        make_business(
            vendor, "Merch Two", Business.BusinessType.PRODUCT_SELLER,
            "merch-two@example.com",
        )
        self.client.force_authenticate(user=vendor)

        response = self.upload(csv_file(self.row("Ambiguous")))

        self.assertEqual(response.data["created"], 0)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertIn("business", response.data["failed"][0]["errors"])

    # ---- whole-file errors ------------------------------------------

    def test_missing_required_column_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(f",{self.category.pk},No Price Column", header="business_id,category_id,name")
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_wrong_file_type_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(csv_file(self.row(), name="products.txt"))

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
        self.assertEqual(Product.objects.count(), 0)

    # ---- permissions ------------------------------------------------

    def test_anonymous_user_is_rejected(self):
        response = self.upload(csv_file(self.row()))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_is_rejected(self):
        self.client.force_authenticate(user=self.customer)

        response = self.upload(csv_file(self.row()))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Product.objects.count(), 0)


class ProductBulkTemplateTests(TestCase):
    def test_template_is_public_and_matches_the_columns(self):
        response = APIClient().get(reverse("product-bulk-template"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv")
        first_line = response.content.decode().splitlines()[0]
        self.assertEqual(first_line, HEADER)


class ProductBulkUploadRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("rules_vendor")
        cls.category = Category.objects.create(name="Rules Supplies")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.vendor)
        self.url = reverse("product-bulk-upload")

    def row(self, business_id="", category=None, name="Rule Item"):
        category = category or self.category
        return f"{business_id},{category.pk},{name},Nice item,25000,5"

    def upload(self, *rows):
        return self.client.post(
            self.url, {"file": csv_file(*rows)}, format="multipart"
        )

    def assert_row_failed(self, response, field):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertIn(field, response.data["failed"][0]["errors"])
        self.assertEqual(Product.objects.count(), 0)

    def test_pending_business_cannot_add_products(self):
        business = make_business(
            self.vendor,
            "Pending Merch",
            Business.BusinessType.PRODUCT_SELLER,
            "pending-merch@example.com",
            verification_status=Business.VerificationStatus.PENDING,
        )

        response = self.upload(self.row(business_id=business.pk))

        self.assert_row_failed(response, "business")

    def test_inactive_business_cannot_add_products(self):
        business = make_business(
            self.vendor,
            "Inactive Merch",
            Business.BusinessType.PRODUCT_SELLER,
            "inactive-merch@example.com",
            is_active=False,
        )

        response = self.upload(self.row(business_id=business.pk))

        self.assert_row_failed(response, "business")

    def test_services_business_cannot_add_products_by_id(self):
        business = make_business(
            self.vendor,
            "Services Only",
            Business.BusinessType.SERVICE_PROVIDER,
            "services-only@example.com",
        )

        response = self.upload(self.row(business_id=business.pk))

        self.assert_row_failed(response, "business")

    def test_blank_business_id_with_only_a_pending_business_fails(self):
        make_business(
            self.vendor,
            "Pending Only",
            Business.BusinessType.PRODUCT_SELLER,
            "pending-only@example.com",
            verification_status=Business.VerificationStatus.PENDING,
        )

        response = self.upload(self.row())

        self.assert_row_failed(response, "business")

    def test_services_category_is_rejected(self):
        make_business(
            self.vendor,
            "Merch For Category",
            Business.BusinessType.PRODUCT_SELLER,
            "merch-category@example.com",
        )
        services_category = Category.objects.create(
            name="Grooming", kind=Category.Kind.SERVICES
        )

        response = self.upload(self.row(category=services_category))

        self.assert_row_failed(response, "category")

    def test_inactive_category_is_rejected(self):
        make_business(
            self.vendor,
            "Merch For Inactive",
            Business.BusinessType.PRODUCT_SELLER,
            "merch-inactive@example.com",
        )
        inactive = Category.objects.create(name="Old Stock", is_active=False)

        response = self.upload(self.row(category=inactive))

        self.assert_row_failed(response, "category")


class ProductBulkUploadApprovalTests(TestCase):
    def test_bulk_uploaded_products_start_unapproved(self):
        vendor = make_vendor("approval_bulk_vendor")
        make_business(
            vendor,
            "Approval Merch",
            Business.BusinessType.PRODUCT_SELLER,
            "approval-merch@example.com",
        )
        category = Category.objects.create(name="Approval Supplies")
        client = APIClient()
        client.force_authenticate(user=vendor)
        row = f",{category.pk},Fresh Item,Nice item,25000,5"

        response = client.post(
            reverse("product-bulk-upload"),
            {"file": csv_file(row)},
            format="multipart",
        )

        self.assertEqual(response.data["created"], 1)
        product = Product.objects.get(name="Fresh Item")
        self.assertFalse(product.approved)
        self.assertNotIn(product, Product.objects.publicly_visible())
