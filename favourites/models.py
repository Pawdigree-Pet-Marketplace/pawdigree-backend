from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


class Favourite(TimeStampedModel):
    """A customer's saved pet OR product (exactly one of the two)."""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favourites",
    )
    pet = models.ForeignKey(
        "pets.Pet",
        on_delete=models.CASCADE,
        related_name="favourites",
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="favourites",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "pet"],
                name="one_favourite_per_customer_pet",
            ),
            models.UniqueConstraint(
                fields=["customer", "product"],
                name="one_favourite_per_customer_product",
            ),
            models.CheckConstraint(
                condition=(
                    Q(pet__isnull=False, product__isnull=True)
                    | Q(pet__isnull=True, product__isnull=False)
                ),
                name="favourite_is_pet_or_product",
            ),
        ]

    def __str__(self):
        return f"{self.customer} likes {self.pet or self.product}"