from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Favourite(TimeStampedModel):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favourites",
    )
    pet = models.ForeignKey(
        "pets.Pet",
        on_delete=models.CASCADE,
        related_name="favourites",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "pet"],
                name="one_favourite_per_customer_pet",
            )
        ]

    def __str__(self):
        return f"{self.customer} likes {self.pet}"
