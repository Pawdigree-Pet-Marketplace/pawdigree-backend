from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from audit.services import record as record_audit
from .availability import booking_tz, free_start_times
from .models import ACTIVE_STATUSES, Booking
from notification.services import after_commit
from .notifications import (
    notify_booking_cancelled,
    notify_booking_created,
    notify_booking_rescheduled,
    notify_booking_status_changed,
)


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
            booking = Booking.objects.create(
                customer=customer, service=service, start_at=start_at,
                end_at=start_at + timedelta(minutes=service.duration), notes=notes,
            )
            after_commit(lambda: notify_booking_created(booking.pk))
            return booking
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


def _apply_booking_status_transition(
    booking,
    new_status,
    reason="",
    *,
    allow_administrative_cancellation=False,
):
    """Validate and persist a transition on an already-locked booking.

    Actor ownership and lookup scopes belong to the public service functions;
    this helper only applies the shared lifecycle rules and the explicitly
    enabled administrator cancellation transitions.
    """
    reason = (reason or "").strip()
    current_status = booking.status

    if current_status == Booking.Status.PENDING:
        allowed_statuses = [Booking.Status.ACCEPTED, Booking.Status.DECLINED]
        if allow_administrative_cancellation:
            allowed_statuses.append(Booking.Status.CANCELLED)
        if new_status not in allowed_statuses:
            allowed = "accepted or declined"
            if allow_administrative_cancellation:
                allowed += " or cancelled"
            raise ValidationError(
                {"status": f"A pending booking can only be {allowed}."}
            )
    elif current_status == Booking.Status.ACCEPTED:
        allowed_statuses = [Booking.Status.COMPLETED]
        if allow_administrative_cancellation:
            allowed_statuses.append(Booking.Status.CANCELLED)
        if new_status not in allowed_statuses:
            allowed = "completed"
            if allow_administrative_cancellation:
                allowed += " or cancelled"
            raise ValidationError(
                {"status": f"An accepted booking can only be {allowed}."}
            )
    else:
        raise ValidationError(
            {
                "status": (
                    f"A {booking.get_status_display().lower()} booking "
                    "can't be changed."
                )
            }
        )

    if new_status == Booking.Status.DECLINED and not reason:
        raise ValidationError(
            {"decision_reason": "A reason is required when declining a booking."}
        )
    if (
        allow_administrative_cancellation
        and new_status == Booking.Status.CANCELLED
        and not reason
    ):
        raise ValidationError(
            {"reason": "A reason is required when an administrator cancels a booking."}
        )
    if (
        new_status == Booking.Status.COMPLETED
        and timezone.now() < booking.end_at
    ):
        raise ValidationError(
            {"status": "A booking can only be completed after it has ended."}
        )

    booking.status = new_status
    update_fields = ["status", "updated_at"]
    if new_status == Booking.Status.DECLINED:
        booking.decision_reason = reason
        update_fields.append("decision_reason")
    booking.save(update_fields=update_fields)
    return booking


def change_booking_status(vendor, booking_id, new_status, decision_reason=""):
    """Apply an allowed vendor transition to one of their bookings."""
    with transaction.atomic():
        try:
            booking = (
                Booking.objects.select_for_update(of=("self",))
                .select_related("service__business")
                .get(
                    pk=booking_id,
                    service__business__vendor=vendor,
                )
            )
        except Booking.DoesNotExist:
            raise NotFound("Booking not found.")

        booking = _apply_booking_status_transition(
            booking,
            new_status,
            decision_reason,
        )
        after_commit(lambda: notify_booking_status_changed(booking.pk, new_status))
        return booking


def admin_change_booking_status(
    *, administrator, booking_id, new_status, reason=""
):
    """Apply an approved administrative transition to any platform booking."""
    reason = (reason or "").strip()
    with transaction.atomic():
        try:
            booking = (
                Booking.objects.select_for_update(of=("self",))
                .select_related("service__business")
                .get(pk=booking_id)
            )
        except Booking.DoesNotExist:
            raise NotFound("Booking not found.")

        previous_status = booking.status
        booking = _apply_booking_status_transition(
            booking,
            new_status,
            reason,
            allow_administrative_cancellation=True,
        )
        record_audit(
            actor=administrator,
            action="booking.status_changed",
            target=booking,
            details={
                "previous_status": previous_status,
                "new_status": new_status,
                "reason": reason,
            },
        )

        after_commit(
            lambda: notify_booking_status_changed(booking.pk, new_status)
        )
        return booking


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
        after_commit(lambda: notify_booking_cancelled(booking.pk))
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
        
        after_commit(lambda: notify_booking_rescheduled(booking.pk))
    return booking
