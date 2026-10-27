from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, ValidationError

from pets.models import Pet

from .models import ACTIVE_STATUSES, AdoptionApplication

ALREADY_APPLIED = 'You already have an open application for this pet.'


def create_adoption_application(customer, pet_id, data):
    """Create an application once the system checks pass.

    Raises NotFound if the pet cannot be applied for, and ValidationError
    if the customer already has an open application for it.
    """
    try:
        pet = Pet.objects.publicly_visible().get(pk=pet_id)
    except Pet.DoesNotExist:
        raise NotFound('This pet is not available.')

    already_applied = AdoptionApplication.objects.filter(
        customer=customer,
        pet=pet,
        status__in=ACTIVE_STATUSES,
    ).exists()
    if already_applied:
        raise ValidationError({'pet': ALREADY_APPLIED})

    try:
        with transaction.atomic():
            return AdoptionApplication.objects.create(
                customer=customer,
                pet=pet,
                **data,
            )
    except IntegrityError:
        # Two submits at the same moment: the database rule stopped the second.
        raise ValidationError({'pet': ALREADY_APPLIED})