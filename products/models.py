from django.conf import settings
from django.db import models

from businesses.models import Business
from categories.models import Category
from common.models import TimeStampedModel
from common.validators import validate_image_upload


class ProductQuerySet(models.QuerySet):
    def publicly_visible(self):
        """Products a customer is allowed to see."""
        return self.filter(
            approved=True,
            is_active=True,
            category__is_active=True,
            business__is_active=True,
            business__verification_status=Business.VerificationStatus.APPROVED,
        )

    def pending_review(self):
        """Active products waiting for an admin decision."""
        return self.filter(approved=False, is_active=True, rejection_reason="")


class Product(TimeStampedModel):
    """Physical merchandise sold by a business on Pawdigree."""

    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    approved = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_products",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name
    
    @property
    def is_available(self):
        return self.is_active and self.stock_quantity > 0

    def send_back_for_review(self, save=True):
        """Put the product back in the admin review queue."""
        self.approved = False
        self.rejection_reason = ""
        self.reviewed_by = None
        self.reviewed_at = None
        if save:
            self.save(
                update_fields=[
                    "approved",
                    "rejection_reason",
                    "reviewed_by",
                    "reviewed_at",
                    "updated_at",
                ]
            )


class ProductImage(models.Model):
    """An image belonging to a physical product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        upload_to="products/%Y/%m/",
        validators=[validate_image_upload],
    )
    alt_text = models.CharField(max_length=150, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "id")

    def __str__(self):
        return f"Image for {self.product.name}"
