from django.conf import settings
from django.db import models
from django.db.models import F, Q

from businesses.models import Business
from common.models import TimeStampedModel
from common.validators import validate_image_upload


class ServiceQuerySet(models.QuerySet):
    def pending_review(self):
        """Active services waiting for an admin decision."""
        return self.filter(approved=False, is_active=True, rejection_reason="")


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
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="services",
    )
    name = models.CharField(max_length=150)
    service_type = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(
        upload_to="services/",
        blank=True,
        null=True,
        validators=[validate_image_upload],
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.PositiveIntegerField()
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE,
    )
    is_active = models.BooleanField(default=True)
    approved = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_services",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    objects = ServiceQuerySet.as_manager()

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def send_back_for_review(self, save=True):
        """Put the service back in the admin review queue."""
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
