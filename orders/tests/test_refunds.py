from decimal import Decimal

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from cart.tests.helpers import make_user
from orders.models import VendorOrder
from orders.services import change_status, mark_refunded
from orders.tests.test_vendor_orders import VendorOrderTestCase

ADMIN_ORDERS = "/api/orders/admin/vendor-orders/"


class RefundTrackingTests(VendorOrderTestCase):
    def setUp(self):
        super().setUp()
        self.system_admin = make_user("sysadmin1", User.Role.SYSTEM_ADMIN)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def cancelled_vendor_order(self, actor=None, reason=""):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)
        change_status(
            vendor_order.pk,
            VendorOrder.Status.CANCELLED,
            actor or self.vendor_one,
            reason,
        )
        vendor_order.refresh_from_db()
        return order, vendor_order

    def test_a_vendor_cancellation_marks_a_refund_as_required(self):
        _, vendor_order = self.cancelled_vendor_order(reason="Out of stock")

        self.assertEqual(
            vendor_order.refund_status, VendorOrder.RefundStatus.REQUIRED
        )
        self.assertEqual(vendor_order.refund_amount, Decimal("20.00"))
        self.assertEqual(vendor_order.cancelled_by, self.vendor_one)
        self.assertIsNotNone(vendor_order.cancelled_at)
        self.assertEqual(vendor_order.cancel_reason, "Out of stock")

    def test_the_other_vendors_order_needs_no_refund(self):
        order, _ = self.cancelled_vendor_order()

        other = self.vendor_order(order, self.business_two)
        self.assertEqual(other.refund_status, VendorOrder.RefundStatus.NONE)
        self.assertEqual(other.refund_amount, Decimal("0.00"))
        self.assertIsNone(other.cancelled_at)

    def test_an_admin_cancellation_also_marks_a_refund_as_required(self):
        _, vendor_order = self.cancelled_vendor_order(actor=self.admin)

        self.assertEqual(
            vendor_order.refund_status, VendorOrder.RefundStatus.REQUIRED
        )
        self.assertEqual(vendor_order.cancelled_by, self.admin)

    def test_a_move_that_is_not_a_cancellation_needs_no_refund(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        change_status(
            vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one
        )

        vendor_order.refresh_from_db()
        self.assertEqual(
            vendor_order.refund_status, VendorOrder.RefundStatus.NONE
        )
        self.assertIsNone(vendor_order.cancelled_at)

    def test_a_vendor_cancellation_is_recorded_in_the_audit_log(self):
        _, vendor_order = self.cancelled_vendor_order()

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "order.status_changed")
        self.assertEqual(entry.actor, self.vendor_one)
        self.assertEqual(entry.target_id, str(vendor_order.pk))
        self.assertEqual(entry.details["to_status"], VendorOrder.Status.CANCELLED)

    def test_an_admin_confirms_the_refund(self):
        _, vendor_order = self.cancelled_vendor_order()

        result = mark_refunded(vendor_order.pk, self.admin)

        self.assertEqual(result.refund_status, VendorOrder.RefundStatus.REFUNDED)
        entry = AuditLog.objects.get(action="order.refund_confirmed")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.details["amount"], "20.00")

    def test_a_refund_cannot_be_confirmed_twice(self):
        _, vendor_order = self.cancelled_vendor_order()
        mark_refunded(vendor_order.pk, self.admin)

        with self.assertRaises(ValidationError):
            mark_refunded(vendor_order.pk, self.admin)

    def test_an_order_that_was_not_cancelled_cannot_be_marked_refunded(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        with self.assertRaises(ValidationError):
            mark_refunded(vendor_order.pk, self.admin)

    def test_a_vendor_cannot_confirm_a_refund(self):
        _, vendor_order = self.cancelled_vendor_order()

        with self.assertRaises(PermissionDenied):
            mark_refunded(vendor_order.pk, self.vendor_one)

    def test_the_vendor_status_endpoint_accepts_a_reason(self):
        order = self.make_paid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        response = self.client_for(self.vendor_one).patch(
            f"/api/orders/vendor/{vendor_order.pk}/status/",
            {"status": "CANCELLED", "reason": "Out of stock"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["refund_status"], "REQUIRED")
        self.assertEqual(response.json()["cancel_reason"], "Out of stock")

    def test_the_admin_refund_endpoint_confirms_a_refund(self):
        _, vendor_order = self.cancelled_vendor_order()

        response = self.client_for(self.admin).post(
            f"{ADMIN_ORDERS}{vendor_order.pk}/refund/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["refund_status"], "REFUNDED")

    def test_vendors_and_customers_cannot_use_the_refund_endpoint(self):
        _, vendor_order = self.cancelled_vendor_order()
        url = f"{ADMIN_ORDERS}{vendor_order.pk}/refund/"

        for user in (self.vendor_one, self.customer):
            response = self.client_for(user).post(url)
            self.assertEqual(response.status_code, 403)

    def test_the_admin_list_can_be_filtered_by_refund_status(self):
        _order, vendor_order = self.cancelled_vendor_order()
        client = self.client_for(self.system_admin)

        response = client.get(ADMIN_ORDERS, {"refund_status": "required"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = data["results"] if isinstance(data, dict) else data
        self.assertEqual([row["id"] for row in rows], [vendor_order.pk])

    def test_an_unknown_refund_status_is_refused(self):
        response = self.client_for(self.system_admin).get(
            ADMIN_ORDERS, {"refund_status": "nope"}
        )

        self.assertEqual(response.status_code, 400)
