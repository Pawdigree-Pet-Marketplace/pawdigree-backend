from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from bookings.availability import booking_tz
from bookings.models import Booking
from bookings.tests.helpers import add_slot, at, future_date, make_service
from cart.tests.helpers import make_business, make_user
from services.models import Service


class CreateBookingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = make_user("booker1", User.Role.CUSTOMER)
        self.other_customer = make_user("booker2", User.Role.CUSTOMER)
        self.vendor = make_user("bookvendor", User.Role.VENDOR)
        self.business = make_business(self.vendor)
        self.service = make_service(self.business, duration=60)
        add_slot(self.service, weekday=0, start_hour=9, end_hour=12)
        self.day = future_date(weekday=0)
        self.url = reverse("booking-create")

    def payload(self, hour=10, minute=0, **extra):
        return {
            "service": self.service.pk,
            "start_at": at(self.day, hour, minute).isoformat(),
            **extra,
        }

    def post(self, user=None, **kwargs):
        if user:
            self.client.force_authenticate(user)
        return self.client.post(self.url, self.payload(**kwargs), format="json")

    def make_booking(self, customer, hour, status_value=Booking.Status.PENDING):
        start = at(self.day, hour)
        return Booking.objects.create(
            customer=customer,
            service=self.service,
            start_at=start,
            end_at=start + timedelta(hours=1),
            status=status_value,
        )

    def test_customer_can_book_a_free_time(self):
        response = self.post(self.customer, notes="Bring vaccination card")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get()
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.service, self.service)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.start_at, at(self.day, 10))
        self.assertEqual(booking.end_at, at(self.day, 11))
        self.assertEqual(booking.notes, "Bring vaccination card")
        self.assertEqual(response.data["status"], "pending")

    def test_taken_time_cannot_be_booked_again(self):
        self.make_booking(self.other_customer, 10)
        response = self.post(self.customer)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_at", response.data)
        self.assertEqual(Booking.objects.count(), 1)

    def test_accepted_time_cannot_be_booked_again(self):
        self.make_booking(self.other_customer, 10, Booking.Status.ACCEPTED)
        response = self.post(self.customer)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelled_time_can_be_booked_again(self):
        self.make_booking(self.other_customer, 10, Booking.Status.CANCELLED)
        response = self.post(self.customer)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_time_between_grid_starts_is_rejected(self):
        response = self.post(self.customer, hour=10, minute=30)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Booking.objects.count(), 0)

    def test_time_outside_the_slot_is_rejected(self):
        response = self.post(self.customer, hour=13)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_past_time_is_rejected(self):
        yesterday = datetime.now(booking_tz()).date() - timedelta(days=1)
        add_slot(self.service, weekday=yesterday.weekday(), start_hour=13, end_hour=15)
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            self.url,
            {
                "service": self.service.pk,
                "start_at": at(yesterday, 13).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unavailable_service_cannot_be_booked(self):
        self.service.availability_status = Service.AvailabilityStatus.UNAVAILABLE
        self.service.save()
        response = self.post(self.customer)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_service_hidden_from_customers_cannot_be_booked(self):
        self.service.approved = False
        self.service.save()
        response = self.post(self.customer)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service", response.data)

    def test_vendor_cannot_book(self):
        response = self.post(self.vendor)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_book(self):
        response = self.post()
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_database_blocks_a_double_booking_that_skips_the_service(self):
        self.make_booking(self.customer, 10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_booking(self.other_customer, 10)

    def test_database_allows_same_time_when_the_first_is_cancelled(self):
        self.make_booking(self.customer, 10, Booking.Status.CANCELLED)
        self.make_booking(self.other_customer, 10)
        self.assertEqual(Booking.objects.count(), 2)