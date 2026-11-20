from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from pets.models import Pet
from reports.models import Report


class ReportModelInvariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reporter = User.objects.create_user(
            username="report_model_reporter",
            email="report-model-reporter@example.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
        )
        vendor = User.objects.create_user(
            username="report_model_vendor",
            email="report-model-vendor@example.com",
            password="TestPassword123!",
            role=User.Role.VENDOR,
        )
        business = Business.objects.create(
            vendor=vendor,
            name="Report Model Business",
            description="Test business",
            contact="+256700000001",
            email="report-model-business@example.com",
            address="Kampala",
            city_district="Central",
        )
        cls.pet = Pet.objects.create(
            vendor=vendor,
            business=business,
            name="Report Model Pet",
            age=12,
            gender=Pet.Gender.UNKNOWN,
            size=Pet.Size.MEDIUM,
        )

    def test_general_report_with_item_id_violates_database_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Report.objects.create(
                    reporter=self.reporter,
                    reason=Report.Reason.OTHER,
                    description="General report must not identify an item.",
                    reported_item_type=Report.ReportedItemType.GENERAL,
                    reported_item_id="123",
                )

        self.assertEqual(Report.objects.count(), 0)

    def test_report_and_target_id_survive_target_deletion(self):
        original_target_id = str(self.pet.pk)
        report = Report.objects.create(
            reporter=self.reporter,
            reason=Report.Reason.OTHER,
            description="This target may later be deleted.",
            reported_item_type=Report.ReportedItemType.PET,
            reported_item_id=original_target_id,
        )

        self.pet.delete()

        retained_report = Report.objects.get(pk=report.pk)
        self.assertEqual(retained_report.reported_item_id, original_target_id)
