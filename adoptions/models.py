import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel

ACTIVE_STATUSES = ('PENDING', 'INFO_REQUESTED')


class AdoptionApplication(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        INFO_REQUESTED = 'INFO_REQUESTED', 'More information requested'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class HomeType(models.TextChoices):
        APARTMENT = 'APARTMENT', 'Apartment'
        HOUSE = 'HOUSE', 'House'
        OTHER = 'OTHER', 'Other'

    class Experience(models.TextChoices):
        NONE = 'NONE', 'First-time owner'
        SOME = 'SOME', 'Some experience'
        EXPERIENCED = 'EXPERIENCED', 'Experienced'

    application_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    pet = models.ForeignKey(
        'pets.Pet',
        on_delete=models.CASCADE,
        related_name='adoption_applications',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='adoption_applications',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    home_type = models.CharField(max_length=20, choices=HomeType.choices)
    has_outdoor_space = models.BooleanField(default=False)
    has_other_pets = models.BooleanField(default=False)
    other_pets_details = models.CharField(max_length=200, blank=True)
    previous_pet_experience = models.CharField(
        max_length=20, choices=Experience.choices
    )
    message = models.TextField(max_length=2000)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='decided_applications',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'pet'],
                condition=Q(status__in=ACTIVE_STATUSES),
                name='one_open_application_per_customer_pet',
            )
        ]

    def __str__(self):
        return f'{self.customer} -> {self.pet} ({self.status})'
    


class AdoptionInfoMessage(TimeStampedModel):
    """One question or answer in an application's information exchange.

    The vendor's requests and the customer's replies are stored as rows,
    so the full conversation stays on the application as a record.
    """

    class Kind(models.TextChoices):
        REQUEST = 'REQUEST', 'Information request'
        REPLY = 'REPLY', 'Applicant reply'

    application = models.ForeignKey(
        AdoptionApplication,
        on_delete=models.CASCADE,
        related_name='info_messages',
    )
    # SET_NULL keeps the conversation if the author's account is deleted.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='adoption_info_messages',
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    body = models.TextField(max_length=2000)

    class Meta:
        # Oldest first. The id breaks ties, so the order is always stable.
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.kind} on {self.application_id}'