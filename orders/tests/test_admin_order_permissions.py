from rest_framework.test import APIClient

from accounts.models import User
from cart.tests.helpers import make_user
from orders.tests.test_vendor_orders import VendorOrderTestCase

ADMIN_ORDERS = "/api/orders/admin/vendor-orders/"


class AdminOrderPermissionTests(VendorOrderTestCase):
    def setUp(self):
        super().setUp()
        self.system_admin = make_user("sysadmin1", User.Role.SYSTEM_ADMIN)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def paid_vendor_order(self):
        order = self.make_paid_order()
        return self.vendor_order(order, self.business_one)

    def test_an_admin_can_list_vendor_orders(self):
        response = self.client_for(self.admin).get(ADMIN_ORDERS)

        self.assertEqual(response.status_code, 200)

    def test_a_system_admin_can_list_vendor_orders(self):
        response = self.client_for(self.system_admin).get(ADMIN_ORDERS)

        self.assertEqual(response.status_code, 200)

    def test_an_admin_can_change_a_vendor_order_status(self):
        vendor_order = self.paid_vendor_order()

        response = self.client_for(self.admin).patch(
            f"{ADMIN_ORDERS}{vendor_order.pk}/status/",
            {"status": "PROCESSING"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "PROCESSING")

    def test_vendors_and_customers_cannot_use_the_admin_order_endpoints(self):
        vendor_order = self.paid_vendor_order()

        for user in (self.vendor_one, self.customer):
            client = self.client_for(user)
            self.assertEqual(client.get(ADMIN_ORDERS).status_code, 403)
            response = client.patch(
                f"{ADMIN_ORDERS}{vendor_order.pk}/status/",
                {"status": "PROCESSING"},
                format="json",
            )
            self.assertEqual(response.status_code, 403)

    def test_an_anonymous_request_is_refused(self):
        response = APIClient().get(ADMIN_ORDERS)

        self.assertIn(response.status_code, (401, 403))
