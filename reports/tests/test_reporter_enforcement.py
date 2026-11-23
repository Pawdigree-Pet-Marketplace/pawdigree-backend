"""
Tests for F60 reporter enforcement and submission throttling.

Covers:
- A report cannot be created without a reporter (DB constraint).
- Deleting a user who has submitted a report is blocked by PROTECT.
- An authenticated submission assigns request.user as reporter.
- Anonymous submissions return 401 and create no report.
- The throttle returns 429 after the configured limit is exceeded.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from pets.models import Pet
from reports.models import Report


def _make_user(username, role=User.Role.CUSTOMER):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="TestPassword123!",
        role=role,
    )


def _make_pet(vendor, business):
    return Pet.objects.create(
        vendor=vendor,
        business=business,
        name="Enforcement Test Pet",
        age=6,
        gender=Pet.Gender.UNKNOWN,
        size=Pet.Size.SMALL,
    )


def _make_business(vendor):
    return Business.objects.create(
        vendor=vendor,
        name="Enforcement Test Business",
        description="Test",
        contact="+256700000099",
        email="enforcement-biz@example.com",
        address="Kampala",
        city_district="Central",
    )


def _pet_payload(pet):
    return {
        "reason": Report.Reason.OTHER,
        "description": "Enforcement test report.",
        "reported_item_type": Report.ReportedItemType.PET,
        "reported_item_id": str(pet.pk),
    }


class ReporterNonNullableModelTests(TestCase):
    """DB-level enforcement: reporter_id must not be NULL."""

    @classmethod
    def setUpTestData(cls):
        vendor = _make_user("enf_vendor", User.Role.VENDOR)
        business = _make_business(vendor)
        cls.pet = _make_pet(vendor, business)

    def test_report_without_reporter_raises_integrity_error(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Report.objects.create(
                    reporter=None,
                    reason=Report.Reason.OTHER,
                    description="No reporter supplied.",
                    reported_item_type=Report.ReportedItemType.PET,
                    reported_item_id=str(self.pet.pk),
                )
        self.assertEqual(Report.objects.count(), 0)


class ReporterProtectOnDeleteTests(TestCase):
    """Deleting a user who owns a report must be blocked by PROTECT."""

    def test_deleting_reporter_is_blocked(self):
        vendor = _make_user("enf_del_vendor", User.Role.VENDOR)
        business = _make_business(vendor)
        pet = _make_pet(vendor, business)
        reporter = _make_user("enf_del_reporter")

        Report.objects.create(
            reporter=reporter,
            reason=Report.Reason.OTHER,
            description="Delete protection test.",
            reported_item_type=Report.ReportedItemType.PET,
            reported_item_id=str(pet.pk),
        )

        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                reporter.delete()

        self.assertTrue(User.objects.filter(pk=reporter.pk).exists())
        self.assertEqual(Report.objects.count(), 1)


class ReporterAssignmentAPITests(TestCase):
    """Authenticated submission assigns request.user as reporter."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = _make_user("enf_api_customer")
        vendor = _make_user("enf_api_vendor", User.Role.VENDOR)
        business = _make_business(vendor)
        cls.pet = _make_pet(vendor, business)

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("report-create")

    def test_authenticated_submission_assigns_request_user_as_reporter(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(self.url, _pet_payload(self.pet), format="json")

        self.assertEqual(response.status_code, 201)
        report = Report.objects.get()
        self.assertEqual(report.reporter_id, self.customer.pk)

    def test_anonymous_submission_returns_401_and_creates_no_report(self):
        response = self.client.post(self.url, _pet_payload(self.pet), format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Report.objects.count(), 0)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "report-throttle-tests",
        }
    },
)
class ReportSubmissionThrottleTests(TestCase):
    """Throttle returns 429 after the configured limit is exceeded."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = _make_user("enf_throttle_customer")
        vendor = _make_user("enf_throttle_vendor", User.Role.VENDOR)
        business = _make_business(vendor)
        cls.pet = _make_pet(vendor, business)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.customer)
        self.url = reverse("report-create")

    def test_throttle_returns_429_after_limit_exceeded(self):
        payload = _pet_payload(self.pet)
        responses = [
            self.client.post(self.url, payload, format="json") for _ in range(6)
        ]
        status_codes = [r.status_code for r in responses]
        self.assertIn(429, status_codes)
        # All responses must be either a successful creation or a throttle rejection.
        for code in status_codes:
            self.assertIn(code, (201, 429))
