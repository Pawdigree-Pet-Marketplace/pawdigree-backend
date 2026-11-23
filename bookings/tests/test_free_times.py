from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from bookings.availability import booking_tz, free_start_times
from bookings.models import Booking
from bookings.tests.helpers import add_slot, at, future_date, make_service
from cart.tests.helpers import make_business, make_user
from services.models import Service


class FreeTimesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = make_user("timesvendor", User.Role.VENDOR)
        self.customer = make_user("timescustomer", User.Role.CUSTOMER)
        self.business = make_business(self.vendor)

# Booking tests need a service-provider business.
        self.business.business_type = Business.BusinessType.SERVICE_PROVIDER
        self.business.save(update_fields=["business_type"])

        self.service = make_service(self.business, duration=60)
        add_slot(self.service, weekday=0, start_hour=9, end_hour=12)
        self.day = future_date(weekday=0)
        self.url = reverse("booking-service-times", args=[self.service.pk])

    def get_times(self, day=None):
        response = self.client.get(self.url, {"date": (day or self.day).isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [datetime.fromisoformat(t) for t in response.data["times"]]

    def book(self, hour, status_value=Booking.Status.PENDING):
        start = at(self.day, hour)
        return Booking.objects.create(
            customer=self.customer,
            service=self.service,
            start_at=start,
            end_at=start + timedelta(minutes=self.service.duration),
            status=status_value,
        )

    def test_times_follow_the_slot_and_service_duration(self):
        self.assertEqual(
            self.get_times(),
            [at(self.day, 9), at(self.day, 10), at(self.day, 11)],
        )

    def test_longer_service_gives_fewer_times(self):
        self.service.duration = 90
        self.service.save()
        self.assertEqual(self.get_times(), [at(self.day, 9), at(self.day, 10, 30)])

    def test_two_slots_on_one_day_are_both_used(self):
        add_slot(self.service, weekday=0, start_hour=14, end_hour=16)
        self.assertEqual(
            self.get_times(),
            [
                at(self.day, 9),
                at(self.day, 10),
                at(self.day, 11),
                at(self.day, 14),
                at(self.day, 15),
            ],
        )

    def test_day_without_slots_has_no_times(self):
        self.assertEqual(self.get_times(self.day + timedelta(days=1)), [])

    def test_pending_booking_removes_its_time(self):
        self.book(10)
        self.assertEqual(self.get_times(), [at(self.day, 9), at(self.day, 11)])

    def test_accepted_booking_removes_its_time(self):
        self.book(10, Booking.Status.ACCEPTED)
        self.assertNotIn(at(self.day, 10), self.get_times())

    def test_cancelled_booking_frees_its_time(self):
        self.book(10, Booking.Status.CANCELLED)
        self.assertIn(at(self.day, 10), self.get_times())

    def test_declined_booking_frees_its_time(self):
        self.book(10, Booking.Status.DECLINED)
        self.assertIn(at(self.day, 10), self.get_times())

    def test_unavailable_service_has_no_times(self):
        self.service.availability_status = Service.AvailabilityStatus.UNAVAILABLE
        self.service.save()
        self.assertEqual(self.get_times(), [])

    def test_service_hidden_from_customers_returns_404(self):
        self.service.approved = False
        self.service.save()
        response = self.client.get(self.url, {"date": self.day.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_past_date_is_rejected(self):
        yesterday = datetime.now(booking_tz()).date() - timedelta(days=1)
        response = self.client.get(self.url, {"date": yesterday.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_or_bad_date_is_rejected(self):
        self.assertEqual(
            self.client.get(self.url).status_code, status.HTTP_400_BAD_REQUEST
        )
        self.assertEqual(
            self.client.get(self.url, {"date": "tomorrow"}).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_times_in_the_past_are_never_offered(self):
        yesterday = datetime.now(booking_tz()).date() - timedelta(days=1)
        add_slot(self.service, weekday=yesterday.weekday(), start_hour=13, end_hour=15)
        self.assertEqual(free_start_times(self.service, yesterday), [])