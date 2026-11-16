from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from bookings.models import Booking
from bookings.services import change_booking_status
from bookings.tests.helpers import make_service
from cart.tests.helpers import make_business, make_user


class VendorBookingStatusTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = make_user("status_vendor", User.Role.VENDOR)
        self.other_vendor = make_user("other_status_vendor", User.Role.VENDOR)
        self.customer = make_user("status_customer", User.Role.CUSTOMER)
        self.business = make_business(self.vendor)
        self.other_business = make_business(self.other_vendor, name="Other Business")
        self.service = make_service(self.business)
        self.other_service = make_service(self.other_business, name="Cat Sitting")

    def make_booking(
        self, status_value=Booking.Status.PENDING, service=None, end_at=None
    ):
        end_at = end_at or (timezone.now() + timedelta(days=1))
        return Booking.objects.create(
            customer=self.customer,
            service=service or self.service,
            start_at=end_at - timedelta(hours=1),
            end_at=end_at,
            status=status_value,
        )

    def update_status(self, booking, status_value, decision_reason=None, user=None):
        self.client.force_authenticate(user=user or self.vendor)
        payload = {"status": status_value}
        if decision_reason is not None:
            payload["decision_reason"] = decision_reason
        return self.client.patch(
            reverse("booking-vendor-status", args=[booking.booking_id]),
            payload,
            format="json",
        )

    def test_vendor_accepts_their_own_pending_booking(self):
        booking = self.make_booking()

        response = self.update_status(booking, Booking.Status.ACCEPTED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["booking_id"], booking.booking_id)
        self.assertEqual(response.data["status"], Booking.Status.ACCEPTED)
        self.assertEqual(response.data["decision_reason"], "")
        self.assertIn("start_at", response.data)
        self.assertIn("end_at", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_vendor_declines_pending_booking_with_trimmed_reason(self):
        booking = self.make_booking()

        response = self.update_status(
            booking, Booking.Status.DECLINED, "  Service unavailable.  "
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.DECLINED)
        self.assertEqual(response.data["decision_reason"], "Service unavailable.")
        booking.refresh_from_db()
        self.assertEqual(booking.decision_reason, "Service unavailable.")

    def test_vendor_completes_accepted_booking_after_end_time(self):
        end_at = timezone.now() - timedelta(minutes=1)
        booking = self.make_booking(
            status_value=Booking.Status.ACCEPTED,
            end_at=end_at,
        )

        response = self.update_status(booking, Booking.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.COMPLETED)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_vendor_can_complete_at_the_exact_end_time(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)

        with patch("bookings.services.timezone.now", return_value=booking.end_at):
            response = self.update_status(booking, Booking.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.COMPLETED)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_declining_without_a_reason_is_rejected(self):
        booking = self.make_booking()

        response = self.update_status(booking, Booking.Status.DECLINED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("decision_reason", response.data)

    def test_declining_with_whitespace_only_reason_is_rejected(self):
        booking = self.make_booking()

        response = self.update_status(booking, Booking.Status.DECLINED, "  \t  ")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("decision_reason", response.data)

    def test_booking_cannot_be_completed_before_its_end_time(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)

        response = self.update_status(booking, Booking.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_pending_booking_cannot_be_completed_directly(self):
        booking = self.make_booking()

        response = self.update_status(booking, Booking.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_declined_booking_cannot_be_accepted(self):
        booking = self.make_booking(status_value=Booking.Status.DECLINED)

        response = self.update_status(booking, Booking.Status.ACCEPTED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_accepted_booking_cannot_be_moved_back_to_pending(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)

        response = self.update_status(booking, Booking.Status.PENDING)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_accepted_booking_cannot_be_declined(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)

        response = self.update_status(
            booking, Booking.Status.DECLINED, "No longer available."
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_completed_booking_cannot_be_updated(self):
        booking = self.make_booking(status_value=Booking.Status.COMPLETED)

        response = self.update_status(booking, Booking.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_cancelled_booking_cannot_be_updated(self):
        booking = self.make_booking(status_value=Booking.Status.CANCELLED)

        response = self.update_status(booking, Booking.Status.ACCEPTED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_vendor_cannot_cancel_a_booking_through_this_endpoint(self):
        booking = self.make_booking()

        response = self.update_status(booking, Booking.Status.CANCELLED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_unsupported_status_is_rejected(self):
        booking = self.make_booking()

        response = self.update_status(booking, "rescheduled")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_vendor_cannot_update_another_vendors_booking(self):
        booking = self.make_booking(service=self.other_service)

        response = self.update_status(booking, Booking.Status.ACCEPTED)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_customer_cannot_use_vendor_status_endpoint(self):
        booking = self.make_booking()

        response = self.update_status(
            booking, Booking.Status.ACCEPTED, user=self.customer
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_use_vendor_status_endpoint(self):
        booking = self.make_booking()
        self.client.force_authenticate(user=None)

        response = self.client.patch(
            reverse("booking-vendor-status", args=[booking.booking_id]),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class VendorBookingStatusConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.vendor = make_user("concurrent_status_vendor", User.Role.VENDOR)
        business = make_business(self.vendor)
        service = make_service(business)
        end_at = timezone.now() + timedelta(days=1)
        self.booking = Booking.objects.create(
            customer=make_user("concurrent_status_customer", User.Role.CUSTOMER),
            service=service,
            start_at=end_at - timedelta(hours=1),
            end_at=end_at,
        )

    def test_conflicting_concurrent_updates_allow_only_one_transition(self):
        barrier = Barrier(2)

        def update_status(target_status):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                change_booking_status(
                    self.vendor,
                    self.booking.booking_id,
                    target_status,
                    "Unavailable." if target_status == Booking.Status.DECLINED else "",
                )
                return "updated"
            except ValidationError:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    update_status,
                    (Booking.Status.ACCEPTED, Booking.Status.DECLINED),
                )
            )

        self.assertCountEqual(results, ["updated", "rejected"])
        self.booking.refresh_from_db()
        self.assertIn(
            self.booking.status,
            (Booking.Status.ACCEPTED, Booking.Status.DECLINED),
        )
