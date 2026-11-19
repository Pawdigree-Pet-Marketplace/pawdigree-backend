from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from pets.models import Pet
from reports.models import Report


class ReportSubmissionAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            username="report_api_customer",
            email="report-api-customer@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        vendor = User.objects.create_user(
            username="report_api_vendor",
            email="report-api-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        business = Business.objects.create(
            vendor=vendor,
            name="Report API Business",
            description="Test business",
            contact="+256700000001",
            email="report-api-business@example.com",
            address="Kampala",
            city_district="Central",
        )
        cls.pet = Pet.objects.create(
            vendor=vendor,
            business=business,
            name="Report API Pet",
            age=12,
            gender=Pet.Gender.UNKNOWN,
            size=Pet.Size.MEDIUM,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("report-create")

    def payload(self, **overrides):
        return {
            "reason": Report.Reason.OTHER,
            "description": "Please review this listing.",
            "reported_item_type": Report.ReportedItemType.PET,
            "reported_item_id": str(self.pet.pk),
            **overrides,
        }

    def authenticate(self):
        self.client.force_authenticate(user=self.customer)

    def assert_response_shape(self, data):
        self.assertEqual(
            set(data),
            {
                "id",
                "reason",
                "description",
                "reported_item_type",
                "reported_item_id",
                "status",
                "created_at",
            },
        )

    def test_authenticated_user_can_submit_pet_report(self):
        self.authenticate()
        payload = self.payload()

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_response_shape(response.data)
        report = Report.objects.get()
        self.assertEqual(report.reporter, self.customer)
        self.assertEqual(report.reason, payload["reason"])
        self.assertEqual(report.description, payload["description"])
        self.assertEqual(
            report.reported_item_type,
            payload["reported_item_type"],
        )
        self.assertEqual(report.reported_item_id, str(self.pet.pk))
        self.assertEqual(report.status, Report.Status.PENDING)
        self.assertEqual(response.data["id"], report.pk)
        self.assertEqual(response.data["status"], Report.Status.PENDING)
        self.assertNotIn("reporter", response.data)

    def test_authenticated_user_can_submit_general_report(self):
        self.authenticate()
        payload = self.payload(
            reported_item_type=Report.ReportedItemType.GENERAL,
        )
        del payload["reported_item_id"]

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_response_shape(response.data)
        report = Report.objects.get()
        self.assertEqual(report.reporter, self.customer)
        self.assertEqual(
            report.reported_item_type,
            Report.ReportedItemType.GENERAL,
        )
        self.assertIsNone(report.reported_item_id)
        self.assertEqual(report.status, Report.Status.PENDING)
        self.assertIsNone(response.data["reported_item_id"])
        self.assertNotIn("reporter", response.data)

    def test_anonymous_submission_is_rejected_without_creating_report(self):
        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Report.objects.count(), 0)

    def test_invalid_payload_is_rejected_without_creating_report(self):
        self.authenticate()
        response = self.client.post(
            self.url,
            self.payload(reason="NOT_A_REASON"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Report.objects.count(), 0)

    def test_reporter_and_status_request_fields_are_rejected(self):
        self.authenticate()

        for field, value in (
            ("reporter", self.customer.pk),
            ("status", "CLOSED"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    self.url,
                    self.payload(**{field: value}),
                    format="json",
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(Report.objects.count(), 0)

    def test_invalid_target_id_is_rejected_without_creating_report(self):
        self.authenticate()
        response = self.client.post(
            self.url,
            self.payload(reported_item_id="not-an-id"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reported_item_id", response.data)
        self.assertEqual(Report.objects.count(), 0)
