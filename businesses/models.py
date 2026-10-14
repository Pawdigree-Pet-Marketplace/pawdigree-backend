
import uuid

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Business(TimeStampedModel):
    """A vendor-owned business on the Pawdigree marketplace."""

    class VerificationStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="businesses",
    )
    name = models.CharField(max_length=150)
    description = models.TextField()
    contact = models.CharField(max_length=30)
    email = models.EmailField()
    address = models.CharField(max_length=255)
    city_district = models.CharField(max_length=100)
    business_hours = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.DRAFT,
    )
    decision_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    logo = models.ImageField(
        upload_to="businesses/logos/",
        blank=True,
        null=True,
    )
    cover_image = models.ImageField(
        upload_to="businesses/covers/",
        blank=True,
        null=True,
    )
    categories = models.ManyToManyField(
        "categories.Category",
        through="BusinessCategory",
        related_name="businesses",
    )

    class Meta:
        db_table = "marketplace_business"
        ordering = ("-created_at",)
        constraints = (
            models.UniqueConstraint(
                fields=["vendor", "name"],
                name="unique_vendor_business_name",
            ),
        )
        indexes = (
           models.Index(
               fields=["verification_status"],
               name="marketplace_verific_763555_idx",
            ),
        )
    def __str__(self):
        return self.name


class BusinessCategory(TimeStampedModel):
    """A business's category selection and its approval status."""

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    business = models.ForeignKey(
        "Business",
        on_delete=models.CASCADE,
        related_name="business_categories",
    )
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="business_categories",
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )

    class Meta:
        db_table = "marketplace_businesscategory"
        constraints = (
            models.UniqueConstraint(
                fields=["business", "category"],
                name="unique_business_category",
            ),
        )

    def __str__(self):
        return f"{self.business.name} - {self.category.name}"


class BusinessImage(TimeStampedModel):
    """Stores multiple appearance images for a business."""

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="business_images/%Y/%m/")
    alt_text = models.CharField(max_length=150, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "marketplace_businessimage"
        ordering = ("display_order", "created_at")

    def __str__(self):
        return f"Image for {self.business.name}"
