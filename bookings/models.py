from django.conf import settings
from django.db import models
from django.db.models import F, Q

from common.models import TimeStampedModel
from services.models import Service

# A booking in one of these statuses holds its time slot.
ACTIVE_STATUSES = ("pending", "accepted")


class Booking(TimeStampedModel):
    """A customer's booking of one service at one time."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    booking_id = models.BigAutoField(primary_key=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)
    decision_reason = models.TextField(blank=True)

    class Meta:
        ordering = ("start_at",)
        constraints = (
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="booking_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["service", "start_at"],
                condition=Q(status__in=ACTIVE_STATUSES),
                name="unique_active_booking_per_service_start",
            ),
        )

    def __str__(self):
        return f"{self.service.name} on {self.start_at:%Y-%m-%d %H:%M}"
