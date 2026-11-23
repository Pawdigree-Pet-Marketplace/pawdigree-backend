from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from accounts.models import User
from audit.models import AuditLog
from bookings import services as booking_services
from bookings.availability import free_start_times
from bookings.models import Booking
from bookings.tests.helpers import add_slot, at, future_date, make_service
from cart.tests.helpers import make_business, make_user
from notification.models import Notification


def admin_change_booking_status(
    *, administrator, booking, new_status, reason=""
):
    """Call the proposed admin service contract without defining production code.

    The implementation stage is expected to provide this keyword-only
    interface in ``bookings.services``:
    ``admin_change_booking_status(administrator=..., booking_id=...,
    new_status=..., reason=...)``.
    """
    service = getattr(booking_services, "admin_change_booking_status", None)
    if service is None:
        raise AssertionError(
            "bookings.services.admin_change_booking_status is not implemented; "
            "see the proposed service contract in this test module."
        )
    return service(
        administrator=administrator,
        booking_id=booking.booking_id,
        new_status=new_status,
        reason=reason,
    )


class AdminBookingServiceTestData:
    def setUp(self):
        super().setUp()
        self.admin = make_user("booking_admin_service", User.Role.ADMIN)
        self.vendor = make_user("booking_vendor_service", User.Role.VENDOR)
        self.other_vendor = make_user(
            "booking_other_vendor_service", User.Role.VENDOR
        )
        self.customer = make_user(
            "booking_customer_service", User.Role.CUSTOMER
        )
        self.business = make_business(self.vendor, name="Admin Test Business")
        self.other_business = make_business(
            self.other_vendor, name="Other Admin Test Business"
        )
        self.service = make_service(self.business, name="Admin Test Service")
        self.other_service = make_service(
            self.other_business, name="Other Admin Test Service"
        )
        self.day = future_date(min_days=3)
        add_slot(self.service, self.day.weekday(), 8, 20)
        add_slot(self.other_service, self.day.weekday(), 8, 20)
        self.next_hour = 8

    def make_booking(
        self,
        *,
        service=None,
        status_value=Booking.Status.PENDING,
        start_at=None,
        end_at=None,
    ):
        if start_at is None:
            if end_at is not None:
                start_at = end_at - timedelta(hours=1)
            else:
                start_at = at(self.day, self.next_hour)
                self.next_hour += 1
        if end_at is None:
            end_at = start_at + timedelta(hours=1)
        return Booking.objects.create(
            customer=self.customer,
            service=service or self.service,
            start_at=start_at,
            end_at=end_at,
            status=status_value,
        )

    def assert_audit(
        self, booking, previous_status, new_status, reason=""
    ):
        entry = AuditLog.objects.get(
            action="booking.status_changed",
            target_type="bookings.booking",
            target_id=str(booking.booking_id),
        )
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.details, {
            "previous_status": previous_status,
            "new_status": new_status,
            "reason": reason,
        })
        self.assertIsNotNone(entry.created_at)


class AdminBookingServiceTests(AdminBookingServiceTestData, TestCase):
    def test_pending_booking_can_be_accepted_and_is_audited(self):
        booking = self.make_booking()

        changed = admin_change_booking_status(
            administrator=self.admin,
            booking=booking,
            new_status=Booking.Status.ACCEPTED,
            reason="Reviewed by support",
        )

        self.assertEqual(changed.status, Booking.Status.ACCEPTED)
        self.assert_audit(
            booking,
            Booking.Status.PENDING,
            Booking.Status.ACCEPTED,
            "Reviewed by support",
        )

    def test_pending_booking_can_be_declined_with_trimmed_reason(self):
        booking = self.make_booking()

        changed = admin_change_booking_status(
            administrator=self.admin,
            booking=booking,
            new_status=Booking.Status.DECLINED,
            reason="  Duplicate request.  ",
        )

        self.assertEqual(changed.status, Booking.Status.DECLINED)
        self.assertEqual(changed.decision_reason, "Duplicate request.")
        self.assert_audit(
            booking,
            Booking.Status.PENDING,
            Booking.Status.DECLINED,
            "Duplicate request.",
        )

    def test_accepted_booking_can_be_completed_after_end_and_is_audited(self):
        end_at = timezone.now() - timedelta(minutes=1)
        booking = self.make_booking(
            status_value=Booking.Status.ACCEPTED,
            start_at=end_at - timedelta(hours=1),
            end_at=end_at,
        )

        changed = admin_change_booking_status(
            administrator=self.admin,
            booking=booking,
            new_status=Booking.Status.COMPLETED,
        )

        self.assertEqual(changed.status, Booking.Status.COMPLETED)
        self.assert_audit(
            booking,
            Booking.Status.ACCEPTED,
            Booking.Status.COMPLETED,
        )

    def test_accepted_booking_can_be_completed_exactly_at_end_at(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)

        with patch(
            "bookings.services.timezone.now", return_value=booking.end_at
        ):
            changed = admin_change_booking_status(
                administrator=self.admin,
                booking=booking,
                new_status=Booking.Status.COMPLETED,
            )

        self.assertEqual(changed.status, Booking.Status.COMPLETED)
        self.assert_audit(
            booking,
            Booking.Status.ACCEPTED,
            Booking.Status.COMPLETED,
        )

    def test_pending_and_accepted_bookings_can_be_cancelled_with_reason(self):
        for initial_status in (
            Booking.Status.PENDING,
            Booking.Status.ACCEPTED,
        ):
            with self.subTest(initial_status=initial_status):
                booking = self.make_booking(status_value=initial_status)

                changed = admin_change_booking_status(
                    administrator=self.admin,
                    booking=booking,
                    new_status=Booking.Status.CANCELLED,
                    reason="  Resolved by administrator.  ",
                )

                self.assertEqual(changed.status, Booking.Status.CANCELLED)
                self.assert_audit(
                    booking,
                    initial_status,
                    Booking.Status.CANCELLED,
                    "Resolved by administrator.",
                )

    def test_decline_and_cancellation_require_a_nonblank_reason(self):
        for current_status, new_status in (
            (Booking.Status.PENDING, Booking.Status.DECLINED),
            (Booking.Status.PENDING, Booking.Status.CANCELLED),
            (Booking.Status.ACCEPTED, Booking.Status.CANCELLED),
        ):
            for reason in ("", "  \t  "):
                with self.subTest(
                    current_status=current_status,
                    new_status=new_status,
                    reason=repr(reason),
                ):
                    booking = self.make_booking(status_value=current_status)

                    with self.assertRaises(ValidationError):
                        admin_change_booking_status(
                            administrator=self.admin,
                            booking=booking,
                            new_status=new_status,
                            reason=reason,
                        )

                    booking.refresh_from_db()
                    self.assertEqual(booking.status, current_status)
                    self.assertEqual(AuditLog.objects.count(), 0)

    def test_completion_before_end_at_is_rejected(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)

        with self.assertRaises(ValidationError):
            admin_change_booking_status(
                administrator=self.admin,
                booking=booking,
                new_status=Booking.Status.COMPLETED,
            )

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_invalid_and_terminal_transitions_are_rejected_without_audit(self):
        invalid_transitions = (
            (Booking.Status.PENDING, Booking.Status.COMPLETED),
            (Booking.Status.ACCEPTED, Booking.Status.PENDING),
            (Booking.Status.ACCEPTED, Booking.Status.DECLINED),
            (Booking.Status.DECLINED, Booking.Status.PENDING),
            (Booking.Status.COMPLETED, Booking.Status.CANCELLED),
            (Booking.Status.CANCELLED, Booking.Status.ACCEPTED),
            (Booking.Status.PENDING, "rescheduled"),
        )
        for current_status, new_status in invalid_transitions:
            with self.subTest(
                current_status=current_status, new_status=new_status
            ):
                booking = self.make_booking(status_value=current_status)

                with self.assertRaises(ValidationError):
                    admin_change_booking_status(
                        administrator=self.admin,
                        booking=booking,
                        new_status=new_status,
                        reason="Reason does not authorize this transition.",
                    )

                booking.refresh_from_db()
                self.assertEqual(booking.status, current_status)
                self.assertEqual(AuditLog.objects.count(), 0)

    def test_admin_can_manage_bookings_from_different_vendor_businesses(self):
        booking = self.make_booking(service=self.other_service)

        changed = admin_change_booking_status(
            administrator=self.admin,
            booking=booking,
            new_status=Booking.Status.ACCEPTED,
        )

        self.assertEqual(changed.status, Booking.Status.ACCEPTED)
        self.assert_audit(
            booking,
            Booking.Status.PENDING,
            Booking.Status.ACCEPTED,
        )

    def test_admin_cancellation_releases_pending_or_accepted_slot(self):
        for initial_status in (
            Booking.Status.PENDING,
            Booking.Status.ACCEPTED,
        ):
            with self.subTest(initial_status=initial_status):
                booking = self.make_booking(status_value=initial_status)
                day = self.day
                self.assertNotIn(
                    booking.start_at,
                    free_start_times(booking.service, day),
                )

                admin_change_booking_status(
                    administrator=self.admin,
                    booking=booking,
                    new_status=Booking.Status.CANCELLED,
                    reason="Duplicate reservation.",
                )

                self.assertIn(
                    booking.start_at,
                    free_start_times(booking.service, day),
                )
