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

    def test_audit_failure_rolls_back_booking_update(self):
        booking = self.make_booking()

        with patch.object(
            booking_services,
            "record_audit",
            side_effect=IntegrityError("audit storage unavailable"),
            create=True,
        ):
            with self.assertRaises(IntegrityError):
                admin_change_booking_status(
                    administrator=self.admin,
                    booking=booking,
                    new_status=Booking.Status.ACCEPTED,
                )

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_rejected_transition_creates_no_audit_entry(self):
        booking = self.make_booking(status_value=Booking.Status.DECLINED)

        with self.assertRaises(ValidationError):
            admin_change_booking_status(
                administrator=self.admin,
                booking=booking,
                new_status=Booking.Status.ACCEPTED,
            )

        self.assertFalse(
            AuditLog.objects.filter(
                action="booking.status_changed",
                target_id=str(booking.booking_id),
            ).exists()
        )

    def test_status_notifications_are_queued_after_commit(self):
        scenarios = (
            (Booking.Status.PENDING, Booking.Status.ACCEPTED, ""),
            (Booking.Status.PENDING, Booking.Status.DECLINED, "Duplicate."),
            (Booking.Status.ACCEPTED, Booking.Status.COMPLETED, ""),
        )
        for current_status, new_status, reason in scenarios:
            with self.subTest(new_status=new_status):
                end_at = (
                    timezone.now() - timedelta(minutes=1)
                    if new_status == Booking.Status.COMPLETED
                    else None
                )
                booking = self.make_booking(
                    status_value=current_status,
                    end_at=end_at,
                )
                with patch.object(
                    booking_services, "notify_booking_status_changed"
                ) as notify:
                    with self.captureOnCommitCallbacks(execute=True) as callbacks:
                        admin_change_booking_status(
                            administrator=self.admin,
                            booking=booking,
                            new_status=new_status,
                            reason=reason,
                        )
                        notify.assert_not_called()

                    self.assertEqual(len(callbacks), 1)
                    notify.assert_called_once_with(booking.booking_id, new_status)

    def test_admin_cancellation_notification_is_queued_after_commit(self):
        booking = self.make_booking()
        with patch.object(
            booking_services,
            "notify_booking_admin_cancelled",
            create=True,
        ) as notify:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                admin_change_booking_status(
                    administrator=self.admin,
                    booking=booking,
                    new_status=Booking.Status.CANCELLED,
                    reason="Internal support note.",
                )
                notify.assert_not_called()

            self.assertEqual(len(callbacks), 1)
            notify.assert_called_once_with(booking.booking_id)

    def test_admin_cancellation_notification_reaches_both_parties_without_reason(
        self,
    ):
        booking = self.make_booking()
        booking.decision_reason = "Do not expose this reason"
        booking.save(update_fields=["decision_reason"])
        notify = getattr(
            __import__("bookings.notifications", fromlist=[
                "notify_booking_admin_cancelled"
            ]),
            "notify_booking_admin_cancelled",
            None,
        )
        self.assertIsNotNone(
            notify,
            "bookings.notifications.notify_booking_admin_cancelled is not "
            "implemented; it must notify customer and vendor without exposing "
            "the administrative reason.",
        )

        notify(booking.booking_id)

        notices = Notification.objects.filter(
            reference_type="booking",
            reference_id=str(booking.booking_id),
        )
        self.assertSetEqual(
            set(notices.values_list("user_id", flat=True)),
            {booking.customer_id, self.vendor.pk},
        )
        self.assertEqual(notices.count(), 2)
        for notice in notices:
            self.assertIn("administrator", notice.message.lower())
            self.assertIn("cancelled", notice.message.lower())
            self.assertEqual(notice.type, Notification.Type.BOOKING_CANCELLED)
            self.assertNotIn("Do not expose this reason", notice.message)

    def test_rejected_admin_cancellation_does_not_schedule_notifications(self):
        booking = self.make_booking(status_value=Booking.Status.DECLINED)
        with patch.object(
            booking_services, "notify_booking_admin_cancelled"
        ) as notify:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(ValidationError):
                    admin_change_booking_status(
                        administrator=self.admin,
                        booking=booking,
                        new_status=Booking.Status.CANCELLED,
                        reason="Not permitted.",
                    )

            self.assertEqual(callbacks, [])
            notify.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)

    def test_existing_vendor_ownership_scope_remains_enforced(self):
        booking = self.make_booking(service=self.other_service)

        with self.assertRaises(NotFound):
            booking_services.change_booking_status(
                self.vendor,
                booking.booking_id,
                Booking.Status.ACCEPTED,
            )

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)


class AdminBookingServiceTransactionTests(
    AdminBookingServiceTestData, TransactionTestCase
):
    reset_sequences = True

    def test_admin_status_notification_waits_for_transaction_commit(self):
        booking = self.make_booking()
        with patch.object(
            booking_services, "notify_booking_status_changed"
        ) as notify:
            with transaction.atomic():
                admin_change_booking_status(
                    administrator=self.admin,
                    booking=booking,
                    new_status=Booking.Status.ACCEPTED,
                )
                notify.assert_not_called()

            notify.assert_called_once_with(
                booking.booking_id,
                Booking.Status.ACCEPTED,
            )

    def test_rollback_discards_audit_and_status_notifications(self):
        booking = self.make_booking()
        with patch.object(
            booking_services, "notify_booking_status_changed"
        ) as notify:
            with self.assertRaisesRegex(RuntimeError, "force rollback"):
                with transaction.atomic():
                    admin_change_booking_status(
                        administrator=self.admin,
                        booking=booking,
                        new_status=Booking.Status.ACCEPTED,
                    )
                    raise RuntimeError("force rollback")

            notify.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertFalse(
            AuditLog.objects.filter(
                action="booking.status_changed",
                target_id=str(booking.booking_id),
            ).exists()
        )

    def test_rollback_discards_admin_cancellation_notifications(self):
        booking = self.make_booking()
        with patch.object(
            booking_services, "notify_booking_admin_cancelled"
        ) as notify:
            with self.assertRaisesRegex(RuntimeError, "force rollback"):
                with transaction.atomic():
                    admin_change_booking_status(
                        administrator=self.admin,
                        booking=booking,
                        new_status=Booking.Status.CANCELLED,
                        reason="Support decision.",
                    )
                    raise RuntimeError("force rollback")

            notify.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertFalse(
            AuditLog.objects.filter(
                action="booking.status_changed",
                target_id=str(booking.booking_id),
            ).exists()
        )

    @skipUnless(
        connection.features.has_select_for_update,
        "The database backend does not provide row-level select_for_update.",
    )
    def test_conflicting_admin_transitions_allow_only_one_update(self):
        booking = self.make_booking()
        barrier = Barrier(2)

        def update(new_status, reason=""):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                admin_change_booking_status(
                    administrator=self.admin,
                    booking=booking,
                    new_status=new_status,
                    reason=reason,
                )
                return "updated"
            except ValidationError:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda values: update(*values),
                    (
                        (Booking.Status.ACCEPTED, ""),
                        (Booking.Status.DECLINED, "Conflict resolved."),
                    ),
                )
            )

        self.assertCountEqual(results, ["updated", "rejected"])
        booking.refresh_from_db()
        self.assertIn(
            booking.status,
            (Booking.Status.ACCEPTED, Booking.Status.DECLINED),
        )
        self.assertEqual(
            AuditLog.objects.filter(
                action="booking.status_changed",
                target_id=str(booking.booking_id),
            ).count(),
            1,
        )
