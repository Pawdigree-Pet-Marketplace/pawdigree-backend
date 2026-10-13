from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        VENDOR = 'VENDOR', 'Vendor'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        unique=True,
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ('username',)


class Business(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING_VERIFICATION = 'PENDING_VERIFICATION', 'Pending Verification'

    vendor = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='businesses',
        limit_choices_to={'role': 'VENDOR'},
    )
    business_name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True)
    business_phone = models.CharField(max_length=20)
    business_email = models.EmailField()
    address = models.CharField(max_length=255)
    city_district = models.CharField(max_length=100)

    logo = models.ImageField(
        upload_to='businesses/logos/',
        blank=True,
        null=True,
    )
    cover_image = models.ImageField(
        upload_to='businesses/covers/',
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.business_name


class BusinessHours(models.Model):
    class Day(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='business_hours',
    )
    day = models.IntegerField(choices=Day.choices)
    is_open = models.BooleanField(default=True)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ['day']
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'day'],
                name='unique_business_hours_per_day',
            ),
        ]

    def __str__(self):
        return f'{self.business.business_name} - {self.get_day_display()}'