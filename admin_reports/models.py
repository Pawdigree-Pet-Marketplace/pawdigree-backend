from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel

TRASH_DAYS = getattr(settings, "REPORT_TRASH_DAYS", 30)


class SavedReportQuerySet(models.QuerySet):
    def _cutoff(self):
        return timezone.now() - timedelta(days=TRASH_DAYS)

    def restorable(self):
        """In the trash and still inside the 30-day window."""
        return self.filter(deleted_at__isnull=False, deleted_at__gte=self._cutoff())

    def expired(self):
        """In the trash for longer than the window: due for permanent deletion."""
        return self.filter(deleted_at__isnull=False, deleted_at__lt=self._cutoff())


class ActiveSavedReportManager(models.Manager):
    """The default manager hides trashed reports from every normal query."""

    def get_queryset(self):
        return SavedReportQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )


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
    filters = models.JSONField(default=dict, blank=True)
    data = models.JSONField()
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="saved_reports",
    )

    # Trash: a report with deleted_at set is "deleted" but still restorable.
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deleted_saved_reports",
    )

    objects = ActiveSavedReportManager()          # active reports only
    all_objects = SavedReportQuerySet.as_manager()  # includes the trash

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(
                fields=("report_type", "-created_at"),
                name="savedreport_type_created_idx",
            ),
            models.Index(fields=("deleted_at",), name="savedreport_deleted_idx"),
        )

    def __str__(self):
        return f"{self.name} ({self.report_type})"

    @property
    def restorable_until(self):
        if self.deleted_at is None:
            return None
        return self.deleted_at + timedelta(days=TRASH_DAYS)

    def soft_delete(self, user):
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])