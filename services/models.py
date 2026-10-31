from django.db import models

from businesses.models import Business
from common.models import TimeStampedModel
from django.db.models import F, Q


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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name
    

class AvailabilitySlot(TimeStampedModel):
    """Weekly time window in which a service can be booked"""
    
    class Weekday(models.IntegerChoices):
        #Match days to Python's date.weekday()
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"
        
    slot_id = models.BigAutoField(primary_key=True)
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="availability_slots"
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    class Meta:
        # Week order first, then earliest slot of the day first.
        ordering = ("weekday", "start_time")
        constraints = (
            # Database-level safety nets. The serializer gives friendly
            # errors first; these protect the data if something bypasses it.
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="slot_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["service", "weekday", "start_time"],
                name="unique_slot_start_per_service_day"
            )
        )
        
    def __str__(self):
        return (
            f"{self.service.name}: {self.get_weekday_display()}"
            f"{self.start_time:%H:%M}-{self.end_time:%H:%M}"
        )
