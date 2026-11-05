from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from documents.models import BusinessDocument

def make_business(vendor, name, status, email):
    return Business.objects.create(
        vendor=vendor,
        name=name,
        description="Pets",
        contact="0700000000",
        email=email,
        address="1 Main St",
        city_district="Kampala",
        business_type=Business.BusinessType.PRODUCT_SELLER,
        verification_status=status,
    )


class SubmissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1", email="admin@example.com",
            password="Test12345!", role=User.Role.ADMIN,
        )
        self.vendor = User.objects.create_user(
            username="vendor1", email="vendor@example.com",
            password="Test12345!", role=User.Role.VENDOR,
        )
        self.other = User.objects.create_user(
            username="vendor2", email="vendor2@example.com",
            password="Test12345!", role=User.Role.VENDOR,
        )
        self.business = make_business(
            self.vendor, "Paws Place",
            Business.VerificationStatus.DRAFT, "shop@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.vendor)

    def submit(self):
        required_types = (
            BusinessDocument.DocumentType.REGISTRATION,
            BusinessDocument.DocumentType.TAX,
        )

        for document_type in required_types:
            if not self.business.documents.filter(
                document_type=document_type
            ).exists():
                BusinessDocument.objects.create(
                    business=self.business,
                    uploaded_by=self.vendor,
                    document_type=document_type,
                    file=f"private_documents/{document_type.lower()}.pdf",
                )

        url = reverse("business-submit", kwargs={"pk": self.business.pk})
        return self.client.post(url)

    def test_submit_moves_draft_to_pending(self):
        response = self.submit()

        self.assertEqual(response.status_code, 200)
        self.business.refresh_from_db()
        self.assertEqual(self.business.verification_status, "pending")

    def test_submit_twice_is_rejected(self):
        self.submit()
        self.assertEqual(self.submit().status_code, 400)

    def test_cannot_submit_another_vendors_business(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.submit().status_code, 404)

    def test_admin_cannot_submit(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.submit().status_code, 403)

    def test_submitted_business_appears_in_admin_queue(self):
        self.submit()

        document = self.business.documents.get(
            document_type=BusinessDocument.DocumentType.REGISTRATION
        )
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse("business-admin-list"))

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [str(self.business.pk)])
        self.assertEqual(len(result["documents"]), 2)
        document_data = next(
            item for item in result["documents"]
            if item["document_id"] == str(document.document_id)
        )
        self.assertEqual(
            document_data["document_id"],
            str(document.document_id),
        )
        self.assertEqual(
            document_data["document_type"],
            BusinessDocument.DocumentType.REGISTRATION,
        )
        self.assertEqual(
            document_data["review_status"],
            BusinessDocument.ReviewStatus.PENDING,
        )
        self.assertIn("created_at", document_data)
        self.assertEqual(
            document_data["download_url"],
            f"/api/documents/{document.document_id}/download/",
        )
        self.assertNotIn("private_documents", str(result["documents"]))

    def test_draft_is_not_in_admin_queue(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse("business-admin-list"))

        self.assertEqual(response.json()["results"], [])

    def test_bad_status_filter_is_rejected(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse("business-admin-list"), {"status": "bogus"})

        self.assertEqual(response.status_code, 400)

    def test_vendor_cannot_see_admin_queue(self):
        response = self.client.get(reverse("business-admin-list"))
        self.assertEqual(response.status_code, 403)

    def test_reply_to_changes_request_resubmits(self):
        self.business.verification_status = "changes_requested"
        self.business.save()
        url = reverse("business-vendor-response", kwargs={"pk": self.business.pk})

        response = self.client.post(url, {"vendor_response": "Added a logo."}, format="json")

        self.assertEqual(response.status_code, 200)
        self.business.refresh_from_db()
        self.assertEqual(self.business.verification_status, "pending")

    def test_reply_without_requested_changes_is_rejected(self):
        url = reverse("business-vendor-response", kwargs={"pk": self.business.pk})

        response = self.client.post(url, {"vendor_response": "Hello"}, format="json")

        self.assertEqual(response.status_code, 400)

    def edit(self):
        url = reverse("business-detail", kwargs={"pk": self.business.pk})
        return self.client.patch(url, {"description": "Updated"}, format="json")

    def test_editing_a_draft_keeps_it_a_draft(self):
        self.assertEqual(self.edit().status_code, 200)
        self.business.refresh_from_db()
        self.assertEqual(self.business.verification_status, "draft")

    def test_suspended_vendor_cannot_reopen_by_editing(self):
        self.business.verification_status = "suspended"
        self.business.save()

        self.assertEqual(self.edit().status_code, 200)
        self.business.refresh_from_db()
        self.assertEqual(self.business.verification_status, "suspended")

    def test_editing_an_approved_business_sends_it_back_to_review(self):
        self.business.verification_status = "approved"
        self.business.save()
        self.vendor.approved = True
        self.vendor.save()

        self.assertEqual(self.edit().status_code, 200)

        self.business.refresh_from_db()
        self.vendor.refresh_from_db()
        self.assertEqual(self.business.verification_status, "pending")
        self.assertFalse(self.vendor.approved)