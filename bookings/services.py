from datetime import timedelta

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from .availability import booking_tz, free_start_times
from .models import Booking


def create_booking(customer, service, start_at, notes=""):
    """Book one free start time of a service for a customer."""
    day = start_at.astimezone(booking_tz()).date()

    # The same list the booking form shows, so the two can't disagree.
    if start_at not in free_start_times(service, day):
        raise ValidationError(
            {"start_at": "This time is not available for this service."}
        )

    try:
        with transaction.atomic():
            return Booking.objects.create(
                customer=customer,
                service=service,
                start_at=start_at,
                end_at=start_at + timedelta(minutes=service.duration),
                notes=notes,
            )
    except IntegrityError:
        # Someone booked the same time between the check and the save.
        raise ValidationError(
            {"start_at": "This time was just booked by someone else."}
        )