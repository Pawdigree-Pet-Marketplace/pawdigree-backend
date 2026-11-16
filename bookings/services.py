from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .availability import booking_tz, free_start_times
from .models import ACTIVE_STATUSES, Booking


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


def _own_booking(customer, booking_id):
    """Lock and return the customer's own booking; anyone else's is a 404."""
    try:
        return (
            Booking.objects.select_for_update()
            .select_related("service")
            .get(pk=booking_id, customer=customer)
        )
    except Booking.DoesNotExist:
        raise NotFound("Booking not found.")


def _require_changeable(booking, action):
    """Only pending or accepted bookings that haven't started can change."""
    if booking.status not in ACTIVE_STATUSES:
        raise ValidationError(
            {
                "status": (
                    f"A {booking.get_status_display().lower()} booking "
                    f"can't be {action}."
                )
            }
        )
    if booking.start_at <= timezone.now():
        raise ValidationError(
            {"start_at": f"A booking that has already started can't be {action}."}
        )


def cancel_booking(customer, booking_id):
    """Cancel the customer's own booking, which frees its time."""
    with transaction.atomic():
        booking = _own_booking(customer, booking_id)
        _require_changeable(booking, "cancelled")
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
    return booking


def reschedule_booking(customer, booking_id, new_start_at):
    """Move the customer's own booking to another free time."""
    with transaction.atomic():
        booking = _own_booking(customer, booking_id)
        _require_changeable(booking, "rescheduled")

        if new_start_at == booking.start_at:
            raise ValidationError({"start_at": "Choose a different time."})

        day = new_start_at.astimezone(booking_tz()).date()
        if new_start_at not in free_start_times(booking.service, day):
            raise ValidationError(
                {"start_at": "This time is not available for this service."}
            )

        booking.start_at = new_start_at
        booking.end_at = new_start_at + timedelta(minutes=booking.service.duration)
        # The vendor has to approve the new time again. To keep the
        # current status instead, delete this line.
        booking.status = Booking.Status.PENDING

        try:
            with transaction.atomic():
                booking.save(update_fields=["start_at", "end_at", "status", "updated_at"])
        except IntegrityError:
            raise ValidationError(
                {"start_at": "This time was just booked by someone else."}
            )
    return booking