from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Report(TimeStampedModel):
    class Reason(models.TextChoices):
        INAPPROPRIATE_CONTENT = (
            "INAPPROPRIATE_CONTENT",
            "Inappropriate content",
        )
        MISLEADING_INFORMATION = (
            "MISLEADING_INFORMATION",
            "Misleading information",
        )
        SUSPECTED_FRAUD = "SUSPECTED_FRAUD", "Suspected fraud or scam"
        OFFENSIVE_CONTENT = "OFFENSIVE_CONTENT", "Offensive or abusive content"
        SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY", "Suspicious activity"
        OTHER = "OTHER", "Other"

    class ReportedItemType(models.TextChoices):
        PET = "PET", "Pet"
        PRODUCT = "PRODUCT", "Product"
        SERVICE = "SERVICE", "Service"
        GENERAL = "GENERAL", "General"
        REVIEW = "REVIEW", "Review"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        DISMISSED = "DISMISSED", "Dismissed"
        RESOLVED = "RESOLVED", "Resolved"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_submitted",
    )
    reason = models.CharField(max_length=22, choices=Reason.choices)
    description = models.TextField()
    reported_item_type = models.CharField(
        max_length=10,
        choices=ReportedItemType.choices,
    )
    reported_item_id = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(reported_item_type="GENERAL")
                    | models.Q(reported_item_id__isnull=True)
                ),
                name="report_general_item_id_null",
            ),
        ]
