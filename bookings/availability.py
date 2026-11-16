from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from services.models import Service

from .models import ACTIVE_STATUSES, Booking


def booking_tz():
    return ZoneInfo(settings.BOOKING_TIME_ZONE)


def free_start_times(service, day):
    """Bookable start times (aware datetimes) for one service on one date.

    Each weekly slot is cut into back-to-back starts the length of the
    service. Times in the past, and times held by a pending or accepted
    booking, are left out. A service marked unavailable has no free times.
    """
    if service.availability_status != Service.AvailabilityStatus.AVAILABLE:
        return []

    tz = booking_tz()
    duration = timedelta(minutes=service.duration)

    candidates = []
    for slot in service.availability_slots.filter(weekday=day.weekday()):
        start = datetime.combine(day, slot.start_time, tzinfo=tz)
        window_end = datetime.combine(day, slot.end_time, tzinfo=tz)
        while start + duration <= window_end:
            candidates.append(start)
            start += duration

    day_start = datetime.combine(day, time.min, tzinfo=tz)
    taken = set(
        Booking.objects.filter(
            service=service,
            status__in=ACTIVE_STATUSES,
            start_at__gte=day_start,
            start_at__lt=day_start + timedelta(days=1),
        ).values_list("start_at", flat=True)
    )

    now = timezone.now()
    return [start for start in candidates if start > now and start not in taken]