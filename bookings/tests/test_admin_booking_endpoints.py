from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import User
from audit.models import AuditLog
from bookings.models import Booking
from bookings.tests.helpers import add_slot, at, future_date, make_service
from cart.tests.helpers import make_business, make_user
from notification.models import Notification


LIST_URL = reverse("admin-booking-list")


def status_url(booking_id):
    return reverse("admin-booking-status", args=[booking_id])


class AdminBookingEndpointTestData:
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = make_user("ep_admin", User.Role.ADMIN)
        self.system_admin = make_user("ep_sysadmin", User.Role.SYSTEM_ADMIN)
        self.vendor = make_user("ep_vendor", User.Role.VENDOR)
        self.other_vendor = make_user("ep_other_vendor", User.Role.VENDOR)
        self.customer = make_user("ep_customer", User.Role.CUSTOMER)

        self.business = make_business(self.vendor, name="EP Business")
        self.other_business = make_business(
            self.other_vendor, name="EP Other Business"
        )
        self.service = make_service(self.business, name="EP Service")
        self.other_service = make_service(
            self.other_business, name="EP Other Service"
        )

        self.day = future_date(min_days=3)
        add_slot(self.service, self.day.weekday(), 8, 20)
        add_slot(self.other_service, self.day.weekday(), 8, 20)
        self._next_hour = 8

    def make_booking(self, *, service=None, status_value=Booking.Status.PENDING,
                     start_at=None, end_at=None):
        if start_at is None:
            if end_at is not None:
                start_at = end_at - timedelta(hours=1)
            else:
                start_at = at(self.day, self._next_hour)
                self._next_hour += 1
        if end_at is None:
            end_at = start_at + timedelta(hours=1)
        return Booking.objects.create(
            customer=self.customer,
            service=service or self.service,
            start_at=start_at,
            end_at=end_at,
            status=status_value,
        )


# ---------------------------------------------------------------------------
# GET /api/admin/bookings/
# ---------------------------------------------------------------------------

class AdminBookingListPermissionTests(AdminBookingEndpointTestData, APITestCase):
    def test_admin_can_list_bookings(self):
        self.make_booking()
        self.client.force_authenticate(self.admin)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_system_admin_can_list_bookings(self):
        self.make_booking()
        self.client.force_authenticate(self.system_admin)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_vendor_cannot_list_bookings(self):
        self.client.force_authenticate(self.vendor)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_list_bookings(self):
        self.client.force_authenticate(self.customer)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_list_bookings(self):
        response = self.client.get(LIST_URL)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class AdminBookingListContentTests(AdminBookingEndpointTestData, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def _results(self, response):
        """Return the results list from a paginated response."""
        return response.data["results"]

    def test_returns_bookings_from_all_vendors(self):
        b1 = self.make_booking(service=self.service)
        b2 = self.make_booking(service=self.other_service)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["booking_id"] for item in self._results(response)}
        self.assertIn(b1.booking_id, ids)
        self.assertIn(b2.booking_id, ids)

    def test_response_contains_expected_fields(self):
        self.make_booking()
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = self._results(response)[0]
        for field in (
            "booking_id", "customer_id", "customer_name",
            "service_id", "service_name",
            "business_id", "business_name",
            "vendor_id", "vendor_name",
            "start_at", "end_at", "status",
            "notes", "decision_reason",
            "created_at", "updated_at",
        ):
            self.assertIn(field, item, f"Missing field: {field}")

    def test_response_does_not_expose_customer_email(self):
        self.make_booking()
        response = self.client.get(LIST_URL)
        item = self._results(response)[0]
        self.assertNotIn("email", item)

    def test_results_ordered_newest_first(self):
        b1 = self.make_booking()
        b2 = self.make_booking()
        response = self.client.get(LIST_URL)
        ids = [item["booking_id"] for item in self._results(response)]
        self.assertGreater(ids.index(b1.booking_id), ids.index(b2.booking_id))

    def test_vendor_and_business_fields_are_correct(self):
        booking = self.make_booking(service=self.service)
        response = self.client.get(LIST_URL)
        item = next(
            i for i in self._results(response)
            if i["booking_id"] == booking.booking_id
        )
        self.assertEqual(item["business_name"], self.business.name)
        self.assertEqual(str(item["business_id"]), str(self.business.pk))
        self.assertEqual(item["vendor_id"], self.vendor.pk)
        self.assertEqual(item["service_name"], self.service.name)
        self.assertEqual(item["customer_id"], self.customer.pk)


# ---------------------------------------------------------------------------
# PATCH /api/admin/bookings/{booking_id}/status/
# ---------------------------------------------------------------------------

class AdminBookingStatusPermissionTests(AdminBookingEndpointTestData, APITestCase):
    def test_admin_can_update_status(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_system_admin_can_update_status(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.system_admin)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_vendor_cannot_update_status(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.vendor)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_update_status(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.customer)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_update_status(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class AdminBookingStatusTransitionTests(AdminBookingEndpointTestData, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_pending_can_be_accepted(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.ACCEPTED)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_pending_can_be_declined_with_reason(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.DECLINED, "reason": "Duplicate."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.DECLINED)

    def test_accepted_can_be_completed_after_end_at(self):
        end_at = timezone.now() - timedelta(minutes=1)
        booking = self.make_booking(
            status_value=Booking.Status.ACCEPTED,
            start_at=end_at - timedelta(hours=1),
            end_at=end_at,
        )
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.COMPLETED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.COMPLETED)

    def test_pending_can_be_cancelled_with_reason(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.CANCELLED, "reason": "Admin decision."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.CANCELLED)

    def test_accepted_can_be_cancelled_with_reason(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.CANCELLED, "reason": "Admin decision."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.CANCELLED)

    def test_decline_without_reason_is_rejected(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.DECLINED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_cancellation_without_reason_is_rejected(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.CANCELLED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_completion_before_end_at_is_rejected(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.COMPLETED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_invalid_transition_is_rejected(self):
        booking = self.make_booking(status_value=Booking.Status.DECLINED)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED, "reason": "Reopen."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_booking_id_returns_404(self):
        response = self.client.patch(
            status_url(999999),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unsupported_status_value_is_rejected(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": "rescheduled"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_response_uses_admin_serializer_fields(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field in ("booking_id", "customer_id", "service_name", "business_name",
                      "vendor_id", "vendor_name", "start_at", "end_at", "status"):
            self.assertIn(field, response.data, f"Missing field: {field}")
        # Verify relational fields are actually populated (L1: select_related check).
        self.assertEqual(response.data["business_name"], self.business.name)
        self.assertEqual(response.data["vendor_id"], self.vendor.pk)
        self.assertEqual(response.data["customer_id"], self.customer.pk)


class AdminBookingStatusSerializerValidationTests(
    AdminBookingEndpointTestData, APITestCase
):
    """Focused tests for M1 (status choice restriction) and M2 (reason validation)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    # --- M1: pending is not a valid target status ---

    def test_pending_is_rejected_as_target_status(self):
        booking = self.make_booking(status_value=Booking.Status.ACCEPTED)
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.PENDING},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    # --- M2: serializer-level reason validation ---

    def test_declined_without_reason_rejected_at_serializer(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.DECLINED, "reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_cancelled_without_reason_rejected_at_serializer(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.CANCELLED, "reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_whitespace_only_reason_rejected_for_declined(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.DECLINED, "reason": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)

    def test_whitespace_only_reason_rejected_for_cancelled(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.CANCELLED, "reason": "\t  \n"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)

    def test_accepted_does_not_require_reason(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_completed_does_not_require_reason(self):
        end_at = timezone.now() - timedelta(minutes=1)
        booking = self.make_booking(
            status_value=Booking.Status.ACCEPTED,
            start_at=end_at - timedelta(hours=1),
            end_at=end_at,
        )
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.COMPLETED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- Regression: existing valid transitions still work ---

    def test_declined_with_reason_succeeds(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.DECLINED, "reason": "Duplicate request."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.DECLINED)

    def test_cancelled_with_reason_succeeds(self):
        booking = self.make_booking()
        response = self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.CANCELLED, "reason": "Admin decision."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Booking.Status.CANCELLED)


class AdminBookingStatusAuditTests(AdminBookingEndpointTestData, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_successful_transition_creates_audit_entry(self):
        booking = self.make_booking()
        self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED},
            format="json",
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="booking.status_changed",
                target_id=str(booking.booking_id),
            ).exists()
        )

    def test_failed_transition_creates_no_audit_entry(self):
        booking = self.make_booking(status_value=Booking.Status.DECLINED)
        self.client.patch(
            status_url(booking.booking_id),
            {"status": Booking.Status.ACCEPTED, "reason": "Reopen."},
            format="json",
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action="booking.status_changed",
                target_id=str(booking.booking_id),
            ).exists()
        )

    def test_cancellation_schedules_admin_cancelled_notification(self):
        booking = self.make_booking()
        with patch(
            "bookings.services.notify_booking_admin_cancelled"
        ) as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.patch(
                    status_url(booking.booking_id),
                    {"status": Booking.Status.CANCELLED, "reason": "Support."},
                    format="json",
                )
            notify.assert_called_once_with(booking.booking_id)

    def test_non_cancellation_schedules_status_changed_notification(self):
        booking = self.make_booking()
        with patch(
            "bookings.services.notify_booking_status_changed"
        ) as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.patch(
                    status_url(booking.booking_id),
                    {"status": Booking.Status.ACCEPTED},
                    format="json",
                )
            notify.assert_called_once_with(
                booking.booking_id, Booking.Status.ACCEPTED
            )

    def test_admin_cancellation_notifies_both_customer_and_vendor(self):
        booking = self.make_booking()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(
                status_url(booking.booking_id),
                {"status": Booking.Status.CANCELLED, "reason": "Support."},
                format="json",
            )
        notices = Notification.objects.filter(
            reference_type="booking",
            reference_id=str(booking.booking_id),
        )
        self.assertEqual(notices.count(), 2)
        self.assertSetEqual(
            set(notices.values_list("user_id", flat=True)),
            {self.customer.pk, self.vendor.pk},
        )
        for notice in notices:
            self.assertNotIn("Support.", notice.message)


# ---------------------------------------------------------------------------
# Regression: existing account-management and vendor/customer routes
# ---------------------------------------------------------------------------

class ExistingRouteRegressionTests(AdminBookingEndpointTestData, APITestCase):
    """Verify that existing SYSTEM_ADMIN-only routes remain protected."""

    def test_admin_cannot_access_user_list(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("admin-user-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_access_administrator_list(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("administrator-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_booking_list_still_scoped_to_vendor(self):
        self.make_booking(service=self.other_service)
        self.client.force_authenticate(self.vendor)
        response = self.client.get(reverse("booking-vendor-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_customer_booking_list_still_scoped_to_customer(self):
        self.make_booking()
        other_customer = make_user("ep_other_cust", User.Role.CUSTOMER)
        self.client.force_authenticate(other_customer)
        response = self.client.get(reverse("booking-customer-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
