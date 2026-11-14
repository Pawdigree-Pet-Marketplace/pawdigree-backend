from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from businesses.models import Business
from categories.models import Category
from services.models import Service
from services.tests.test_bulk_upload import csv_file, make_business, make_vendor


class BulkUploadedServicesNeedApprovalTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = make_vendor("bulk_approval_vendor")
        self.business = make_business(
            self.vendor,
            "Bulk Approval Services",
            Business.BusinessType.SERVICE_PROVIDER,
            "bulk-approval@example.com",
        )
        self.category = Category.objects.create(
            name="Bulk Approval Grooming", kind=Category.Kind.SERVICES
        )
        self.client.force_authenticate(user=self.vendor)
        self.url = reverse("service-bulk-upload")

    def test_bulk_uploaded_services_start_unapproved(self):
        rows = (
            f",{self.category.pk},Dog Grooming,Grooming,Bath and trim,30000,60,",
            f",{self.category.pk},Cat Grooming,Grooming,Brush and trim,25000,45,",
        )

        response = self.client.post(
            self.url, {"file": csv_file(*rows)}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        services = Service.objects.filter(business=self.business)
        self.assertEqual(services.count(), 2)
        self.assertFalse(services.filter(approved=True).exists())

    def test_bulk_uploaded_services_are_hidden_from_customers(self):
        row = f",{self.category.pk},Dog Grooming,Grooming,Bath and trim,30000,60,"

        self.client.post(
            self.url, {"file": csv_file(row)}, format="multipart"
        )
        response = APIClient().get(reverse("service-public-list"))

        self.assertEqual(response.data["count"], 0)

    def test_bulk_uploaded_services_appear_in_the_pending_queue(self):
        row = f",{self.category.pk},Dog Grooming,Grooming,Bath and trim,30000,60,"

        self.client.post(
            self.url, {"file": csv_file(row)}, format="multipart"
        )

        self.assertEqual(Service.objects.pending_review().count(), 1)
