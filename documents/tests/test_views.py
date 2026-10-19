import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from businesses.models import Business
from documents.models import BusinessDocument


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
