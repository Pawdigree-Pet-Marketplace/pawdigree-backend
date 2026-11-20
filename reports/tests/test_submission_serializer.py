from django.core.validators import MaxValueValidator
from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from pets.models import Pet
from products.models import Product
from reports.models import Report
from services.models import Service

from reports.serializers import ReportSubmissionSerializer


class ReportSubmissionSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="report_serializer_vendor",
            email="report-serializer-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Report Test Business",
            description="Test business",
            contact="+256700000001",
            email="report-business@example.com",
            address="Kampala",
            city_district="Central",
        )
        cls.merchandise_category = Category.objects.create(
            name="Report Test Products",
            kind=Category.Kind.MERCHANDISE,
        )
        cls.pet = Pet.objects.create(
            vendor=cls.vendor,
            business=cls.business,
            name="Report Test Pet",
            age=12,
            gender=Pet.Gender.UNKNOWN,
            size=Pet.Size.MEDIUM,
        )
        cls.product = Product.objects.create(
            business=cls.business,
            category=cls.merchandise_category,
            name="Report Test Product",
            description="Product for serializer tests",
            price="10.00",
        )
        cls.service = Service.objects.create(
            business=cls.business,
            name="Report Test Service",
            service_type="Grooming",
            description="Service for serializer tests",
            price="10.00",
            duration=30,
        )

    def payload(self, target_type, item_id=None, **overrides):
        data = {
            "reason": "OTHER",
            "description": "Please review this item.",
            "reported_item_type": target_type,
        }
        if item_id is not None:
            data["reported_item_id"] = str(item_id)
        data.update(overrides)
        return data

    def assert_valid(self, data):
        serializer = ReportSubmissionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.validated_data

    def assert_invalid(self, data, field):
        serializer = ReportSubmissionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn(field, serializer.errors)

    def test_pet_product_and_service_targets_are_valid(self):
        targets = (
            ("PET", self.pet),
            ("PRODUCT", self.product),
            ("SERVICE", self.service),
        )

        for target_type, target in targets:
            with self.subTest(target_type=target_type):
                values = self.assert_valid(
                    self.payload(target_type, target.pk)
                )
                self.assertEqual(values["reported_item_id"], str(target.pk))

    def test_general_report_accepts_omitted_or_null_item_id(self):
        omitted = self.assert_valid(self.payload("GENERAL"))
        explicit_null = self.assert_valid(
            self.payload("GENERAL", reported_item_id=None)
        )

        self.assertNotIn("reported_item_id", omitted)
        self.assertIsNone(explicit_null["reported_item_id"])

    def test_listing_target_requires_item_id(self):
        for target_type in ("PET", "PRODUCT", "SERVICE"):
            with self.subTest(target_type=target_type):
                self.assert_invalid(self.payload(target_type), "reported_item_id")

    def test_general_report_rejects_supplied_item_id(self):
        self.assert_invalid(
            self.payload("GENERAL", self.pet.pk),
            "reported_item_id",
        )

    def test_malformed_and_nonexistent_ids_are_rejected(self):
        for target_type in ("PET", "PRODUCT", "SERVICE"):
            with self.subTest(target_type=target_type, case="malformed"):
                self.assert_invalid(
                    self.payload(target_type, "not-an-id"),
                    "reported_item_id",
                )
            with self.subTest(target_type=target_type, case="missing row"):
                self.assert_invalid(
                    self.payload(target_type, "987654321"),
                    "reported_item_id",
                )

    def test_out_of_range_primary_key_ids_are_rejected_before_lookup(self):
        targets = (
            ("PET", Pet),
            ("PRODUCT", Product),
            ("SERVICE", Service),
        )

        for target_type, model in targets:
            with self.subTest(target_type=target_type):
                max_validator = next(
                    validator
                    for validator in model._meta.pk.validators
                    if isinstance(validator, MaxValueValidator)
                )
                max_value = max_validator.limit_value
                if callable(max_value):
                    max_value = max_value()
                out_of_range_id = str(max_value + 1)

                serializer = ReportSubmissionSerializer(
                    data=self.payload(target_type, out_of_range_id)
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn("reported_item_id", serializer.errors)

    def test_id_is_checked_only_against_the_declared_target_model(self):
        pet = Pet.objects.create(
            pet_id=701,
            vendor=self.vendor,
            business=self.business,
            name="Typed Target Pet",
            age=6,
            gender=Pet.Gender.UNKNOWN,
            size=Pet.Size.SMALL,
        )
        product = Product.objects.create(
            id=702,
            business=self.business,
            category=self.merchandise_category,
            name="Typed Target Product",
            price="1.00",
        )
        service = Service.objects.create(
            service_id=703,
            business=self.business,
            name="Typed Target Service",
            service_type="Grooming",
            description="Typed target",
            price="1.00",
            duration=15,
        )

        for target_type, wrong_id in (
            ("PET", product.pk),
            ("PRODUCT", service.pk),
            ("SERVICE", pet.pk),
        ):
            with self.subTest(target_type=target_type):
                self.assert_invalid(
                    self.payload(target_type, wrong_id),
                    "reported_item_id",
                )

    def test_review_and_other_unsupported_types_are_rejected(self):
        for target_type in ("REVIEW", "UNKNOWN"):
            with self.subTest(target_type=target_type):
                self.assert_invalid(
                    self.payload(target_type),
                    "reported_item_type",
                )

    def test_invalid_reason_is_rejected(self):
        self.assert_invalid(
            self.payload("GENERAL", reason="NOT_A_REASON"),
            "reason",
        )

    def test_all_report_reason_choices_are_accepted(self):
        for reason, _label in Report.Reason.choices:
            with self.subTest(reason=reason):
                values = self.assert_valid(
                    self.payload("GENERAL", reason=reason)
                )
                self.assertEqual(values["reason"], reason)

    def test_missing_or_over_limit_description_is_rejected(self):
        missing = self.payload("GENERAL")
        del missing["description"]
        self.assert_invalid(missing, "description")
        self.assert_invalid(
            self.payload("GENERAL", description="   "),
            "description",
        )

        too_many_words = self.payload("GENERAL", description="word " * 301)
        self.assert_invalid(too_many_words, "description")

        too_many_characters = self.payload("GENERAL", description="x" * 3001)
        self.assert_invalid(too_many_characters, "description")

    def test_existing_inactive_unapproved_rejected_and_sold_targets_are_valid(self):
        targets = (
            (
                "PET",
                Pet.objects.create(
                    vendor=self.vendor,
                    business=self.business,
                    name="Inactive rejected adopted pet",
                    age=24,
                    gender=Pet.Gender.UNKNOWN,
                    size=Pet.Size.LARGE,
                    is_active=False,
                    approved=False,
                    rejection_reason="Needs review",
                    adoption_status=Pet.AdoptionStatus.ADOPTED,
                ),
            ),
            (
                "PRODUCT",
                Product.objects.create(
                    business=self.business,
                    category=self.merchandise_category,
                    name="Inactive rejected out-of-stock product",
                    price="1.00",
                    stock_quantity=0,
                    is_active=False,
                    approved=False,
                    rejection_reason="Needs review",
                ),
            ),
            (
                "SERVICE",
                Service.objects.create(
                    business=self.business,
                    name="Inactive rejected service",
                    service_type="Grooming",
                    description="Needs review",
                    price="1.00",
                    duration=15,
                    is_active=False,
                    approved=False,
                    rejection_reason="Needs review",
                ),
            ),
        )

        for target_type, target in targets:
            with self.subTest(target_type=target_type):
                self.assert_valid(self.payload(target_type, target.pk))

    def test_unavailable_service_is_valid_report_target(self):
        service = Service.objects.create(
            business=self.business,
            name="Unavailable Report Target",
            service_type="Grooming",
            description="Currently unavailable",
            price="1.00",
            duration=15,
            availability_status=Service.AvailabilityStatus.UNAVAILABLE,
        )

        values = self.assert_valid(self.payload("SERVICE", service.pk))

        self.assertEqual(values["reported_item_id"], str(service.pk))

    def test_reporter_status_and_other_fields_are_not_accepted(self):
        for extra in (
            {"reporter": self.vendor.pk},
            {"status": "CLOSED"},
            {"id": 10},
            {"created_at": "2026-01-01T00:00:00Z"},
            {"updated_at": "2026-01-01T00:00:00Z"},
        ):
            with self.subTest(field=next(iter(extra))):
                self.assert_invalid(
                    self.payload("GENERAL", **extra),
                    next(iter(extra)),
                )
