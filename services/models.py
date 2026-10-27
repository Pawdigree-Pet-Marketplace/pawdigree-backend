from django.db import models

from businesses.models import Business
from common.models import TimeStampedModel


class Service(TimeStampedModel):
    """A service offered by a vendor-owned business."""

    service_id = models.BigAutoField(primary_key=True)

    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "available", "Available"
        UNAVAILABLE = "unavailable", "Unavailable"

    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="services",
    )
    name = models.CharField(max_length=150)
    service_type = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.PositiveIntegerField()
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name
