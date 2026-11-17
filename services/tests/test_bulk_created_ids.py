from rest_framework import status

from businesses.models import Business
from categories.models import Category
from services.models import Service
from services.tests.test_bulk_upload import (
    BulkTestCase,
    csv_file,
    make_business,
    make_vendor,
)


class ServiceBulkCreatedIdsTests(BulkTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor("svc_ids_vendor")
        cls.category = Category.objects.create(
            name="Bulk Ids Grooming", kind=Category.Kind.SERVICES
        )
        cls.business = make_business(
            cls.vendor,
            "Bulk Ids Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "bulk-ids-services@example.com",
        )

    def test_response_lists_the_ids_of_the_created_services(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(self.row("First Service"), self.row("Second Service"))
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(
            sorted(response.data["created_ids"]),
            sorted(
                Service.objects.filter(business=self.business).values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_a_failed_row_adds_no_id(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            csv_file(
                self.row("Good Service"),
                self.row("Bad Service", price="not-a-number"),
            )
        )

        self.assertEqual(response.data["created"], 1)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertEqual(
            response.data["created_ids"],
            [Service.objects.get(name="Good Service").pk],
        )
