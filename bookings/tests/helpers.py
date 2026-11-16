from datetime import datetime, time, timedelta

from bookings.availability import booking_tz
from businesses.models import BusinessCategory
from categories.models import Category
from services.models import AvailabilitySlot, Service


def make_service(business, name="Dog Grooming", duration=60, **extra):
    """A service that passes every public visibility rule."""
    category, _ = Category.objects.get_or_create(
        name="Booking Grooming", defaults={"kind": Category.Kind.SERVICES}
    )
    BusinessCategory.objects.get_or_create(
        business=business,
        category=category,
        defaults={"approval_status": BusinessCategory.ApprovalStatus.APPROVED},
    )
    return Service.objects.create(
        business=business,
        category=category,
        name=name,
        service_type="Grooming",
        description="Bath and trim",
        price="30000",
        duration=duration,
        approved=True,
        **extra,
    )


def add_slot(service, weekday, start_hour, end_hour):
    return AvailabilitySlot.objects.create(
        service=service,
        weekday=weekday,
        start_time=time(start_hour),
        end_time=time(end_hour),
    )


def future_date(weekday=0, min_days=2):
    """The first date at least min_days ahead that falls on this weekday."""
    day = datetime.now(booking_tz()).date() + timedelta(days=min_days)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def at(day, hour, minute=0):
    """An aware datetime on that date in the booking time zone."""
    return datetime.combine(day, time(hour, minute), tzinfo=booking_tz())