from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from bookings.availability import free_start_times
from bookings.models import Booking
from bookings.tests.helpers import add_slot, at, future_date, make_service
from cart.tests.helpers import make_business, make_user
from services.models import Service


class BookingChangeTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = make_user("changer1", User.Role.CUSTOMER)
        self.other_customer = make_user("changer2", User.Role.CUSTOMER)
        self.vendor = make_user("changevendor", User.Role.VENDOR)
        self.business = make_business(self.vendor)
        self.service = make_service(self.business, duration=60)
        add_slot(self.service, weekday=0, start_hour=9, end_hour=12)
        self.day = future_date(weekday=0)

    def make_booking(
        self, customer=None, hour=10, status_value=Booking.Status.PENDING
    ):
        start = at(self.day, hour)
        return Booking.objects.create(
            customer=customer or self.customer,
            service=self.service,
            start_at=start,
            end_at=start + timedelta(hours=1),
            status=status_value,
        )

    def make_started_booking(self):
        start = timezone.now() - timedelta(days=1)
        return Booking.objects.create(
            customer=self.customer,
            service=self.service,
            start_at=start,
            end_at=start + timedelta(hours=1),
        )

    def cancel(self, booking, user=None):
        self.client.force_authenticate(user or self.customer)
        return self.client.post(reverse("booking-cancel", args=[booking.pk]))

    def reschedule(self, booking, hour, user=None, minute=0):
        self.client.force_authenticate(user or self.customer)
        return self.client.post(
            reverse("booking-reschedule", args=[booking.pk]),
            {"start_at": at(self.day, hour, minute).isoformat()},
            format="json",
        )


class CancelBookingTests(BookingChangeTestCase):
    def test_customer_can_cancel_a_pending_booking(self):
        booking = self.make_booking()
        response = self.cancel(booking)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "cancelled")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_customer_can_cancel_an_accepted_booking(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)
        response = self.cancel(booking)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_customer_can_cancel_after_vendor_accepts_the_booking(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.vendor)
        vendor_response = self.client.patch(
            reverse("booking-vendor-status", args=[booking.pk]),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(vendor_response.status_code, status.HTTP_200_OK)

        response = self.cancel(booking)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.CANCELLED)

    def test_cancelling_frees_the_time(self):
        booking = self.make_booking()
        self.assertNotIn(at(self.day, 10), free_start_times(self.service, self.day))
        self.cancel(booking)
        self.assertIn(at(self.day, 10), free_start_times(self.service, self.day))

    def test_finished_bookings_cannot_be_cancelled(self):
        for hour, status_value in enumerate(
            (
                Booking.Status.CANCELLED,
                Booking.Status.COMPLETED,
                Booking.Status.DECLINED,
            ),
            start=9,
        ):
            with self.subTest(status=status_value):
                booking = self.make_booking(hour=hour, status_value=status_value)
                response = self.cancel(booking)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                booking.refresh_from_db()
                self.assertEqual(booking.status, status_value)

    def test_started_booking_cannot_be_cancelled(self):
        booking = self.make_started_booking()
        response = self.cancel(booking)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_another_customers_booking_returns_404(self):
        booking = self.make_booking(customer=self.other_customer)
        response = self.cancel(booking)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_unknown_booking_returns_404(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(reverse("booking-cancel", args=[999999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendor_cannot_cancel(self):
        booking = self.make_booking()
        response = self.cancel(booking, user=self.vendor)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_cancel(self):
        booking = self.make_booking()
        response = self.client.post(reverse("booking-cancel", args=[booking.pk]))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class RescheduleBookingTests(BookingChangeTestCase):
    def test_customer_can_move_a_pending_booking(self):
        booking = self.make_booking(hour=10)
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.start_at, at(self.day, 11))
        self.assertEqual(booking.end_at, at(self.day, 12))
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_moving_an_accepted_booking_sends_it_back_to_pending(self):
        booking = self.make_booking(hour=10, status_value=Booking.Status.ACCEPTED)
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "pending")

    def test_customer_can_reschedule_after_vendor_accepts_the_booking(self):
        booking = self.make_booking(hour=10)
        self.client.force_authenticate(self.vendor)
        vendor_response = self.client.patch(
            reverse("booking-vendor-status", args=[booking.pk]),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(vendor_response.status_code, status.HTTP_200_OK)

        response = self.reschedule(booking, hour=11)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.PENDING)

    def test_old_time_is_freed_and_new_time_is_held(self):
        booking = self.make_booking(hour=10)
        self.reschedule(booking, hour=11)
        times = free_start_times(self.service, self.day)
        self.assertIn(at(self.day, 10), times)
        self.assertNotIn(at(self.day, 11), times)

    def test_taken_time_is_rejected(self):
        self.make_booking(customer=self.other_customer, hour=11)
        booking = self.make_booking(hour=10)
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        booking.refresh_from_db()
        self.assertEqual(booking.start_at, at(self.day, 10))

    def test_same_time_is_rejected(self):
        booking = self.make_booking(hour=10)
        response = self.reschedule(booking, hour=10)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_time_outside_the_slots_is_rejected(self):
        booking = self.make_booking(hour=10)
        self.assertEqual(
            self.reschedule(booking, hour=13).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.reschedule(booking, hour=10, minute=30).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_unavailable_service_rejects_a_move(self):
        booking = self.make_booking(hour=10)
        self.service.availability_status = Service.AvailabilityStatus.UNAVAILABLE
        self.service.save()
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelled_booking_cannot_be_moved(self):
        booking = self.make_booking(status_value=Booking.Status.CANCELLED)
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_started_booking_cannot_be_moved(self):
        booking = self.make_started_booking()
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_at_is_required(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            reverse("booking-reschedule", args=[booking.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_at", response.data)

    def test_another_customers_booking_returns_404(self):
        booking = self.make_booking(customer=self.other_customer)
        response = self.reschedule(booking, hour=11)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        booking.refresh_from_db()
        self.assertEqual(booking.start_at, at(self.day, 10))

    def test_vendor_cannot_reschedule(self):
        booking = self.make_booking()
        response = self.reschedule(booking, hour=11, user=self.vendor)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_reschedule(self):
        booking = self.make_booking()
        response = self.client.post(
            reverse("booking-reschedule", args=[booking.pk]),
            {"start_at": at(self.day, 11).isoformat()},
            format="json",
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
