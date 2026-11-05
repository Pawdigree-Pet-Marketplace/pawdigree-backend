
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
        REGISTRATION = "REGISTRATION", "Business Trading Licence"
        TAX = "TAX", "Tax Records"
        OTHER = "OTHER", "Other"
        PROFESSIONAL_CERTIFICATE = (
            "PROFESSIONAL_CERTIFICATE",
            "Professional Certificate",
        )
        SUPPORTING_DOCUMENT = "SUPPORTING_DOCUMENT", "Supporting Document"

    class ReviewStatus(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes requested"
        SUPERSEDED = "SUPERSEDED", "Superseded"

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
        max_length=30,
        choices=DocumentType.choices,
        default=DocumentType.REGISTRATION,
    )
    review_status = models.CharField(
        max_length=25,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )
    correction_reason = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replacement_versions",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_business_documents",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    file = models.FileField(
        storage=private_document_storage,
        upload_to=private_document_upload_path,
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("previous_version",),
                condition=models.Q(previous_version__isnull=False),
                name="unique_business_document_replacement",
            ),
        ]

    def __str__(self):
        return f"{self.document_type} — {self.business.name}"


class BusinessDocumentReview(TimeStampedModel):
    class Action(models.TextChoices):
        APPROVE = "APPROVE", "Approve"
        REQUEST_CHANGES = "REQUEST_CHANGES", "Request changes"

    document = models.ForeignKey(
        BusinessDocument,
        on_delete=models.PROTECT,
        related_name="review_history",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="business_document_reviews",
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )
    correction_reason = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.action} — {self.document.document_id}"
