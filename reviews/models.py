from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import path, include

from common.models import TimeStampedModel


class Review(TimeStampedModel):
    """One customer's rating and comment for one product, service or pet."""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    # Exactly one of these three is filled in. The constraint below enforces it.
    product = models.ForeignKey(
        "products.Product", null=True, blank=True,
        on_delete=models.CASCADE, related_name="reviews",
    )
    service = models.ForeignKey(
        "services.Service", null=True, blank=True,
        on_delete=models.CASCADE, related_name="reviews",
    )
    pet = models.ForeignKey(
        "pets.Pet", null=True, blank=True,
        on_delete=models.CASCADE, related_name="reviews",
    )

    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(max_length=1000, blank=True, default="")
    # Admins can hide an abusive review without deleting it.
    is_visible = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = (
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5),
                name="review_rating_between_1_and_5",
            ),
            models.CheckConstraint(
                condition=(
                    Q(product__isnull=False, service__isnull=True, pet__isnull=True)
                    | Q(product__isnull=True, service__isnull=False, pet__isnull=True)
                    | Q(product__isnull=True, service__isnull=True, pet__isnull=False)
                ),
                name="review_exactly_one_target",
            ),
            # One review per customer per item. Each is conditional because 
            # the other two columns are NULL for any given row.
            models.UniqueConstraint(
                fields=("customer", "product"),
                condition=Q(product__isnull=False),
                name="one_review_per_customer_product",
            ),
            models.UniqueConstraint(
                fields=("customer", "service"),
                condition=Q(service__isnull=False),
                name="one_review_per_customer_service",
            ),
            models.UniqueConstraint(
                fields=("customer", "pet"),
                condition=Q(pet__isnull=False),
                name="one_review_per_customer_pet",
            ),
        )

    @property
    def target_kind(self):
        """'product', 'service' or 'pet', whichever this review is for."""
        for kind in ("product", "service", "pet"):
            if getattr(self, f"{kind}_id") is not None:
                return kind

    @property
    def target_pk(self):
        return getattr(self, f"{self.target_kind}_id")

    def __str__(self):
        return f"{self.rating}★ {self.target_kind} {self.target_pk} by {self.customer_id}"
