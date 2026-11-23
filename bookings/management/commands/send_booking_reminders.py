from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.models import Booking
from bookings.notifications import notify_booking_reminder


class Command(BaseCommand):
    help = "Remind customers of accepted bookings that start within 24 hours."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        now = timezone.now()
        ids = list(
            Booking.objects.filter(
                status=Booking.Status.ACCEPTED,
                start_at__gt=now,
                start_at__lte=now + timedelta(hours=options["hours"]),
            ).values_list("pk", flat=True)
        )
        for booking_id in ids:
            notify_booking_reminder(booking_id)  # skips ones already sent
        self.stdout.write(f"Checked {len(ids)} booking(s).")