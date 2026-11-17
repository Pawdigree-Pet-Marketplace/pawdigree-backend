from rest_framework.exceptions import ValidationError

from accounts.models import User
from audit.models import AuditLog
from cart.tests.helpers import make_user
from orders.models import VendorOrder
from orders.services import change_status
from orders.tests.test_vendor_orders import VendorOrderTestCase


class OrderStatusAuditTests(VendorOrderTestCase):
    def setUp(self):
        super().setUp()
        self.system_admin = make_user("sysadmin1", User.Role.SYSTEM_ADMIN)

    def paid_vendor_order(self):
        order = self.make_paid_order()
        return order, self.vendor_order(order, self.business_one)

    def test_an_admin_change_is_recorded(self):
        order, vendor_order = self.paid_vendor_order()

        change_status(
            vendor_order.pk, VendorOrder.Status.PROCESSING, self.admin
        )

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "order.status_changed")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.actor_role, self.admin.role)
        self.assertEqual(entry.target_type, "orders.vendororder")
        self.assertEqual(entry.target_id, str(vendor_order.pk))
        self.assertEqual(
            entry.details,
            {
                "from_status": VendorOrder.Status.PAID,
                "to_status": VendorOrder.Status.PROCESSING,
                "order": str(order.pk),
            },
        )

    def test_a_system_admin_change_is_recorded(self):
        _, vendor_order = self.paid_vendor_order()

        change_status(
            vendor_order.pk, VendorOrder.Status.PROCESSING, self.system_admin
        )

        entry = AuditLog.objects.get()
        self.assertEqual(entry.actor, self.system_admin)

    def test_a_vendor_change_is_not_recorded(self):
        _, vendor_order = self.paid_vendor_order()

        change_status(
            vendor_order.pk, VendorOrder.Status.PROCESSING, self.vendor_one
        )

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_an_unpaid_order_change_is_refused_and_not_recorded(self):
        order = self.make_unpaid_order()
        vendor_order = self.vendor_order(order, self.business_one)

        with self.assertRaises(ValidationError):
            change_status(
                vendor_order.pk, VendorOrder.Status.PROCESSING, self.admin
            )

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_a_move_that_is_not_allowed_is_refused_and_not_recorded(self):
        _, vendor_order = self.paid_vendor_order()

        with self.assertRaises(ValidationError):
            change_status(
                vendor_order.pk, VendorOrder.Status.DELIVERED, self.admin
            )

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_an_admin_cancel_is_recorded_and_returns_the_stock(self):
        _, vendor_order = self.paid_vendor_order()
        self.assertEqual(self.stock(self.toy), 3)

        change_status(
            vendor_order.pk, VendorOrder.Status.CANCELLED, self.admin
        )

        self.assertEqual(self.stock(self.toy), 5)
        entry = AuditLog.objects.get()
        self.assertEqual(
            entry.details["to_status"], VendorOrder.Status.CANCELLED
        )
