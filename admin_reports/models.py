from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class SavedReport(TimeStampedModel):
    """A frozen snapshot of a report, kept so admins can compare periods."""

    class ReportType(models.TextChoices):
        OVERVIEW = "overview", "Overview"
        USERS = "users", "Users"
        PETS = "pets", "Pets"
        PRODUCT_SALES = "product-sales", "Product sales"
        PET_SALES = "pet-sales", "Pet sales"

    name = models.CharField(max_length=150)
    report_type = models.CharField(max_length=20, choices=ReportType.choices)
    # The filters used, so the frontend can offer "Run again".
    filters = models.JSONField(default=dict, blank=True)
    # The full report exactly as it looked when saved.
    data = models.JSONField()
    # SET_NULL keeps the report if the admin's account is deleted.
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="saved_reports",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(
                fields=("report_type", "-created_at"),
                name="savedreport_type_created_idx",
            ),
        )

    def __str__(self):
        return f"{self.name} ({self.report_type})"
