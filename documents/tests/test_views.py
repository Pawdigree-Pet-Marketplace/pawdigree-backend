import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from businesses.models import Business
from documents.models import (
    BusinessDocument,
    BusinessDocumentReview,
    private_document_storage,
)


@pytest.fixture
def vendor_business(db, vendor):
    return Business.objects.create(
        vendor=vendor,
        name="Happy Paws",
        description="Pet care services",
        contact="+256700123456",
        email="happypaws@example.com",
        address="Kampala Road",
        city_district="Kampala",
    )


@pytest.fixture
def another_vendor_business(db, another_vendor):
    return Business.objects.create(
        vendor=another_vendor,
        name="Another Happy Paws",
        description="Pet care services",
        contact="+256700123457",
        email="anotherhappypaws@example.com",
        address="Entebbe Road",
        city_district="Wakiso",
    )


def make_document():
    return SimpleUploadedFile(
        "registration.pdf",
        b"%PDF-1.4 test document content",
        content_type="application/pdf",
    )


@pytest.mark.django_db
class TestBusinessDocumentUpload:
    url = reverse("business-document-upload")

    def test_vendor_can_upload_document_for_own_business(
        self, api_client, vendor, vendor_business, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            self.url,
            {
                "business": str(vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": make_document(),
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert BusinessDocument.objects.filter(
            business=vendor_business,
            uploaded_by=vendor,
        ).exists()

    def test_vendor_cannot_upload_document_for_another_business(
        self, api_client, vendor, another_vendor_business
    ):
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            self.url,
            {
                "business": str(another_vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": make_document(),
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not BusinessDocument.objects.filter(
            business=another_vendor_business
        ).exists()

    def test_customer_cannot_upload_document(
        self, api_client, customer, vendor_business
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            self.url,
            {
                "business": str(vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": make_document(),
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_user_cannot_upload_document(
        self, api_client, vendor_business
    ):
        response = api_client.post(
            self.url,
            {
                "business": str(vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": make_document(),
            },
            format="multipart",
        )

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_rejects_unsupported_file_extension(
        self, api_client, vendor, vendor_business
    ):
        api_client.force_authenticate(user=vendor)
        uploaded_file = SimpleUploadedFile(
            "malware.exe",
            b"MZ fake executable",
            content_type="application/octet-stream",
        )

        response = api_client.post(
            self.url,
            {
                "business": str(vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": uploaded_file,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_file_with_mismatched_signature(
        self, api_client, vendor, vendor_business
    ):
        api_client.force_authenticate(user=vendor)
        uploaded_file = SimpleUploadedFile(
            "fake.pdf",
            b"not a real PDF",
            content_type="application/pdf",
        )

        response = api_client.post(
            self.url,
            {
                "business": str(vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": uploaded_file,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_file_larger_than_10_mb(
        self, api_client, vendor, vendor_business
    ):
        api_client.force_authenticate(user=vendor)
        uploaded_file = SimpleUploadedFile(
            "large.pdf",
            b"%PDF-" + b"x" * (10 * 1024 * 1024),
            content_type="application/pdf",
        )

        response = api_client.post(
            self.url,
            {
                "business": str(vendor_business.pk),
                "document_type": "REGISTRATION",
                "file": uploaded_file,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestBusinessDocumentDownload:
    def test_admin_can_download_document(
        self, api_client, admin, vendor, vendor_business, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        document = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file=make_document(),
        )
        api_client.force_authenticate(user=admin)

        response = api_client.get(
            reverse(
                "business-document-download",
                kwargs={"document_id": document.document_id},
            )
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Disposition"].startswith("attachment;")
        response.close()
        document.file.delete(save=False)

    def test_missing_file_returns_404_not_500(
        self, api_client, admin, vendor, vendor_business, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        document = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file=make_document(),
        )
        document.file.storage.delete(document.file.name)
        api_client.force_authenticate(user=admin)

        response = api_client.get(
            reverse(
                "business-document-download",
                kwargs={"document_id": document.document_id},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "no longer available" in response.data["detail"]

    def test_record_without_a_file_returns_404(
        self, api_client, admin, vendor, vendor_business
    ):
        document = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file="",
        )
        api_client.force_authenticate(user=admin)

        response = api_client.get(
            reverse(
                "business-document-download",
                kwargs={"document_id": document.document_id},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_vendor_cannot_download_document(
        self, api_client, vendor, vendor_business, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        document = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file=make_document(),
        )
        api_client.force_authenticate(user=vendor)

        response = api_client.get(
            reverse(
                "business-document-download",
                kwargs={"document_id": document.document_id},
            )
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        document.file.delete(save=False)

    def test_customer_cannot_download_document(
        self, api_client, customer, vendor, vendor_business, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        document = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file=make_document(),
        )
        api_client.force_authenticate(user=customer)

        response = api_client.get(
            reverse(
                "business-document-download",
                kwargs={"document_id": document.document_id},
            )
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        document.file.delete(save=False)

    def test_unauthenticated_user_cannot_download_document(
        self, api_client, vendor, vendor_business
    ):
        document = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file=make_document(),
        )

        response = api_client.get(
            reverse(
                "business-document-download",
                kwargs={"document_id": document.document_id},
            )
        )

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
        document.file.delete(save=False)


@pytest.mark.django_db
class TestBusinessDocumentReview:
    def create_document(self, vendor_business, vendor):
        return BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type="REGISTRATION",
            file="private_documents/registration.pdf",
        )

    def review(self, api_client, document, data):
        return api_client.post(
            reverse(
                "business-document-review",
                kwargs={"document_id": document.document_id},
            ),
            data,
            format="json",
        )

    def test_admin_can_approve_document(
        self, api_client, admin, vendor, vendor_business
    ):
        document = self.create_document(vendor_business, vendor)
        api_client.force_authenticate(user=admin)

        response = self.review(api_client, document, {"action": "APPROVE"})

        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.review_status == BusinessDocument.ReviewStatus.APPROVED
        assert document.correction_reason == ""
        assert document.reviewed_by == admin
        assert document.reviewed_at is not None
        assert document.review_history.count() == 1
        review = document.review_history.get()
        assert review.action == BusinessDocumentReview.Action.APPROVE
        assert review.reviewed_by == admin
        assert response.data["review_status"] == document.review_status
        assert response.data["correction_reason"] == ""

    def test_admin_can_request_document_corrections(
        self, api_client, admin, vendor, vendor_business
    ):
        document = self.create_document(vendor_business, vendor)
        api_client.force_authenticate(user=admin)
        reason = "Please upload a clearer registration certificate."

        response = self.review(
            api_client,
            document,
            {
                "action": "REQUEST_CHANGES",
                "correction_reason": reason,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert (
            document.review_status
            == BusinessDocument.ReviewStatus.CHANGES_REQUESTED
        )
        assert document.correction_reason == reason
        assert document.reviewed_by == admin
        review = document.review_history.get()
        assert review.action == BusinessDocumentReview.Action.REQUEST_CHANGES
        assert review.correction_reason == reason
        assert response.data["correction_reason"] == reason

    def test_request_changes_requires_reason(
        self, api_client, admin, vendor, vendor_business
    ):
        document = self.create_document(vendor_business, vendor)
        api_client.force_authenticate(user=admin)

        response = self.review(
            api_client,
            document,
            {"action": "REQUEST_CHANGES"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        document.refresh_from_db()
        assert document.review_status == BusinessDocument.ReviewStatus.PENDING
        assert document.review_history.count() == 0

    def test_vendor_cannot_review_document(
        self, api_client, vendor, vendor_business
    ):
        document = self.create_document(vendor_business, vendor)
        api_client.force_authenticate(user=vendor)

        response = self.review(api_client, document, {"action": "APPROVE"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert document.review_history.count() == 0

    def test_already_reviewed_document_cannot_be_reviewed_again(
        self, api_client, admin, vendor, vendor_business
    ):
        document = self.create_document(vendor_business, vendor)
        document.review_status = BusinessDocument.ReviewStatus.APPROVED
        document.save(update_fields=["review_status"])
        api_client.force_authenticate(user=admin)

        response = self.review(
            api_client,
            document,
            {
                "action": "REQUEST_CHANGES",
                "correction_reason": "Try again.",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert document.review_history.count() == 0


@pytest.mark.django_db
class TestBusinessDocumentResubmission:
    def create_document(self, business, vendor):
        return BusinessDocument.objects.create(
            business=business,
            uploaded_by=vendor,
            document_type=BusinessDocument.DocumentType.REGISTRATION,
            file="private_documents/registration.pdf",
            review_status=BusinessDocument.ReviewStatus.CHANGES_REQUESTED,
            correction_reason="Please upload a clearer copy.",
        )

    def resubmit(self, api_client, document, file):
        return api_client.post(
            reverse(
                "business-document-resubmit",
                kwargs={"document_id": document.document_id},
            ),
            {"file": file},
            format="multipart",
        )

    def test_vendor_can_resubmit_corrected_document(
        self, api_client, vendor, vendor_business, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            private_document_storage, "location", str(tmp_path)
        )
        original = self.create_document(vendor_business, vendor)
        api_client.force_authenticate(user=vendor)

        response = self.resubmit(api_client, original, make_document())

        assert response.status_code == status.HTTP_201_CREATED
        original.refresh_from_db()
        replacement = BusinessDocument.objects.get(previous_version=original)
        assert original.review_status == BusinessDocument.ReviewStatus.SUPERSEDED
        assert replacement.review_status == BusinessDocument.ReviewStatus.PENDING
        assert replacement.version == 2
        assert replacement.document_type == original.document_type
        assert replacement.business == vendor_business
        assert replacement.uploaded_by == vendor
        assert response.data["version"] == 2
        assert response.data["review_status"] == "PENDING"
        replacement.file.delete(save=False)

    def test_vendor_cannot_resubmit_another_vendors_document(
        self, api_client, vendor, another_vendor_business
    ):
        original = self.create_document(
            another_vendor_business,
            another_vendor_business.vendor,
        )
        api_client.force_authenticate(user=vendor)

        response = self.resubmit(api_client, original, make_document())

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_document_without_requested_changes_cannot_be_resubmitted(
        self, api_client, vendor, vendor_business
    ):
        original = BusinessDocument.objects.create(
            business=vendor_business,
            uploaded_by=vendor,
            document_type=BusinessDocument.DocumentType.REGISTRATION,
            file="private_documents/registration.pdf",
            review_status=BusinessDocument.ReviewStatus.PENDING,
        )
        api_client.force_authenticate(user=vendor)

        response = self.resubmit(api_client, original, make_document())

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        original.refresh_from_db()
        assert original.review_status == BusinessDocument.ReviewStatus.PENDING
        assert not BusinessDocument.objects.filter(
            previous_version=original
        ).exists()

    def test_replacement_preserves_original_review_history(
        self, api_client, admin, vendor, vendor_business, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            private_document_storage, "location", str(tmp_path)
        )
        original = self.create_document(vendor_business, vendor)
        review = BusinessDocumentReview.objects.create(
            document=original,
            reviewed_by=admin,
            action=BusinessDocumentReview.Action.REQUEST_CHANGES,
            correction_reason="Please upload a clearer copy.",
        )
        api_client.force_authenticate(user=vendor)

        response = self.resubmit(api_client, original, make_document())

        assert response.status_code == status.HTTP_201_CREATED
        original.refresh_from_db()
        assert original.review_history.count() == 1
        assert original.review_history.get() == review
        replacement = BusinessDocument.objects.get(previous_version=original)
        replacement.file.delete(save=False)

    def test_replacement_rejects_invalid_file(
        self, api_client, vendor, vendor_business
    ):
        original = self.create_document(vendor_business, vendor)
        api_client.force_authenticate(user=vendor)
        invalid_file = SimpleUploadedFile(
            "fake.pdf",
            b"not a real PDF",
            content_type="application/pdf",
        )

        response = self.resubmit(api_client, original, invalid_file)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        original.refresh_from_db()
        assert (
            original.review_status
            == BusinessDocument.ReviewStatus.CHANGES_REQUESTED
        )
        assert not BusinessDocument.objects.filter(
            previous_version=original
        ).exists()
