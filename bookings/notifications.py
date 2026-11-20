from notification.models import Notification
from notification.services import create_notification

from .availability import booking_tz
from .models import Booking

T = Notification.Type


def _load(booking_id):
    return Booking.objects.select_related(
        "service__business__vendor", "customer"
    ).get(pk=booking_id)


def _when(booking):
    return booking.start_at.astimezone(booking_tz()).strftime("%a %d %b, %H:%M")


def _vendor_notice(booking, ntype, message, key):
    business = booking.service.business
    create_notification(
        business.vendor, ntype, message,
        reference_id=booking.pk, reference_type="booking",
        business=business, event_key=key,
    )


def notify_booking_created(booking_id):
    booking = _load(booking_id)
    _vendor_notice(
        booking, T.BOOKING_NEW,
        f"New booking request for {booking.service.name} on {_when(booking)}.",
        f"booking-new:{booking.pk}",
    )


def notify_booking_status_changed(booking_id, new_status):
    """Vendor accepted, declined or completed: tell the customer."""
    booking = _load(booking_id)
    name, when = booking.service.name, _when(booking)
    if new_status == Booking.Status.ACCEPTED:
        message = f"Your booking for {name} on {when} was confirmed."
    elif new_status == Booking.Status.DECLINED:
        reason = f" Reason: {booking.decision_reason}" if booking.decision_reason else ""
        message = f"Your booking for {name} on {when} was declined.{reason}"
    elif new_status == Booking.Status.COMPLETED:
        message = f"Your booking for {name} is complete. You can now leave a review."
    else:
        return
    create_notification(
        booking.customer, T.BOOKING_UPDATED, message,
        reference_id=booking.pk, reference_type="booking",
        event_key=f"booking-status:{booking.pk}:{new_status}",
    )


def notify_booking_cancelled(booking_id):
    booking = _load(booking_id)
    _vendor_notice(
        booking, T.BOOKING_CANCELLED,
        f"A customer cancelled the booking for {booking.service.name} on {_when(booking)}.",
        f"booking-cancelled:{booking.pk}",
    )


def notify_booking_rescheduled(booking_id):
    booking = _load(booking_id)
    _vendor_notice(
        booking, T.BOOKING_RESCHEDULED,
        f"A customer moved their booking for {booking.service.name} to "
        f"{_when(booking)}. It needs your approval again.",
        f"booking-rescheduled:{booking.pk}:{int(booking.start_at.timestamp())}",
    )


def notify_booking_reminder(booking_id):
    """Idempotent: running the job twice sends one reminder per start time."""
    booking = _load(booking_id)
    if booking.status != Booking.Status.ACCEPTED:
        return
    create_notification(
        booking.customer, T.BOOKING_REMINDER,
        f"Reminder: your booking for {booking.service.name} is on {_when(booking)}.",
        reference_id=booking.pk, reference_type="booking",
        event_key=f"booking-reminder:{booking.pk}:{int(booking.start_at.timestamp())}",
    )