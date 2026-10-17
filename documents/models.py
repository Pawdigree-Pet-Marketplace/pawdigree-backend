import uuid

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel
from .storage import PrivateDocumentStorage


private_document_storage = PrivateDocumentStorage()


def private_document_upload_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    suffix = f".{extension}" if extension else ""
    return f"private_documents/{uuid.uuid4().hex}{suffix}"


class BusinessDocument(TimeStampedModel):
    class DocumentType(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Business registration"
        TAX = "TAX", "Tax document"
        OTHER = "OTHER", "Other"

    document_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.PROTECT,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_business_documents",
    )
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.REGISTRATION,
    )
    file = models.FileField(
        storage=private_document_storage,
        upload_to=private_document_upload_path,
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.document_type} — {self.business.name}"
