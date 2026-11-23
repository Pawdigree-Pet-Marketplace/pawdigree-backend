"""Tests for the admin endpoints that record refunds for payments."""

from decimal import Decimal

from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog
from orders.models import Order
from payments import tests as pt
from payments.models import Payment, PaymentRefund
from payments.services import process_gateway_event, start_payment

LIST_URL = "payment-admin-refunds"
MARK_URL = "payment-admin-mark-refunded"


class AdminRefundTestCase(pt.SandboxCase):
    """self.payment is a payment that arrived after its order expired."""

    def setUp(self):
        super().setUp()
        self.admin = pt.make_user("admin@test.com", User.Role.ADMIN)
        self.system_admin = pt.make_user("sysadmin@test.com", User.Role.SYSTEM_ADMIN)
        self.payment = start_payment(self.customer, self.order.pk, "pesapal")
        self.pay_late(self.payment, self.order)

    def pay_late(self, payment, order):
        self.expire_order(order)
        process_gateway_event(self.event(payment))
        return self.reload(payment)

    def second_payment(self):
        customer = pt.make_user("customer2@test.com", User.Role.CUSTOMER)
        order = pt.make_order(customer, self.product, 1)
        payment = start_payment(customer, order.pk, "pesapal")
        return customer, order, payment

    def refund_body(self, **overrides):
        body = {
            "amount": "100000.00",
            "gateway_reference": "RF-1",
            "reason": "Paid after the order expired.",
        }
        body.update(overrides)
        return body

    def mark(self, payment, user=None, **overrides):
        return self.api_client(user or self.admin).post(
            reverse(MARK_URL, args=[payment.pk]),
            self.refund_body(**overrides),
            format="json",
        )

    def listing(self, user=None, **params):
        return self.api_client(user or self.admin).get(reverse(LIST_URL), params)


class AccessTests(AdminRefundTestCase):
    def test_login_is_required(self):
        anonymous = self.api_client()
        self.assertEqual(anonymous.get(reverse(LIST_URL)).status_code, 401)
        response = anonymous.post(
            reverse(MARK_URL, args=[self.payment.pk]), self.refund_body(), format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_customers_and_vendors_are_refused(self):
        for user in (self.customer, self.vendor):
            with self.subTest(role=user.role):
                self.assertEqual(self.listing(user).status_code, 403)
                self.assertEqual(self.mark(self.payment, user).status_code, 403)
        self.assertEqual(PaymentRefund.objects.count(), 0)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)

    def test_admin_and_system_admin_can_list(self):
        for user in (self.admin, self.system_admin):
            with self.subTest(role=user.role):
                self.assertEqual(self.listing(user).status_code, 200)


class ListTests(AdminRefundTestCase):
    def test_lists_only_payments_that_need_a_refund_by_default(self):
        _, _, paid = self.second_payment()
        process_gateway_event(self.event(paid))
        self.reload(paid)
        self.assertEqual(paid.status, Payment.Status.PAID)

        body = self.listing().json()
        self.assertEqual(body["count"], 1)
        row = body["results"][0]
        self.assertEqual(row["id"], self.payment.pk)
        self.assertEqual(row["order_id"], self.order.pk)
        self.assertEqual(row["order_status"], "EXPIRED")
        self.assertEqual(row["status"], "REFUND_REQUIRED")
        self.assertEqual(row["amount"], "100000.00")
        self.assertEqual(row["currency"], "UGX")
        self.assertEqual(row["gateway_reference"], self.payment.gateway_reference)
        self.assertIn("after the order", row["failure_reason"])
        self.assertEqual(
            row["customer"],
            {"id": self.customer.pk, "name": "Test User", "email": "customer@test.com"},
        )
        self.assertIsNone(row["received_amount"])
        self.assertIsNone(row["refund"])
        self.assertNotIn("gateway_payload", row)

    def test_invalid_status_is_refused(self):
        self.assertEqual(self.listing(status="PAID").status_code, 400)
        self.assertEqual(self.listing(status="nonsense").status_code, 400)

    def test_refunded_payments_are_listed_with_their_record(self):
        self.mark(self.payment)
        self.assertEqual(self.listing().json()["count"], 0)

        body = self.listing(status="refunded").json()
        self.assertEqual(body["count"], 1)
        refund = body["results"][0]["refund"]
        self.assertEqual(refund["amount"], "100000.00")
        self.assertEqual(refund["gateway_reference"], "RF-1")
        self.assertEqual(refund["reason"], "Paid after the order expired.")
        self.assertEqual(refund["refunded_by"]["id"], self.admin.pk)
        self.assertIn("refunded_at", refund)

    def test_shows_what_the_gateway_received_when_the_amount_was_wrong(self):
        _customer, _order, payment = self.second_payment()
        process_gateway_event(
            self.event(
                payment,
                amount=Decimal("120000.00"),
                payload={"amount": "120000.00"},
            )
        )
        rows = {row["id"]: row for row in self.listing().json()["results"]}
        self.assertEqual(rows[payment.pk]["received_amount"], "120000.00")
        self.assertEqual(rows[payment.pk]["amount"], "50000.00")


class MarkRefundedTests(AdminRefundTestCase):
    def test_records_the_refund_and_marks_the_payment_refunded(self):
        response = self.mark(self.payment)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "REFUNDED")
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUNDED)

        refund = PaymentRefund.objects.get(payment=self.payment)
        self.assertEqual(refund.refunded_by, self.admin)
        self.assertEqual(refund.amount, Decimal("100000.00"))
        self.assertEqual(refund.currency, "UGX")
        self.assertEqual(refund.reason, "Paid after the order expired.")
        self.assertEqual(refund.gateway_reference, "RF-1")
        self.assertIsNotNone(refund.created_at)

    def test_writes_an_audit_entry_without_the_reason_text(self):
        self.mark(self.payment)

        entry = AuditLog.objects.get(action="payment.refund_confirmed")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_type, "payments.payment")
        self.assertEqual(entry.target_id, str(self.payment.pk))
        self.assertEqual(entry.details["amount"], "100000.00")
        self.assertEqual(entry.details["gateway_reference"], "RF-1")
        self.assertNotIn("reason", entry.details)

    def test_system_admin_can_record_a_refund(self):
        response = self.mark(self.payment, self.system_admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PaymentRefund.objects.get().refunded_by, self.system_admin
        )

    def test_a_smaller_refund_is_accepted(self):
        self.assertEqual(self.mark(self.payment, amount="40000.00").status_code, 200)
        self.assertEqual(PaymentRefund.objects.get().amount, Decimal("40000.00"))

    def test_the_order_and_stock_are_left_alone(self):
        stock = self.stock_now()
        self.mark(self.payment)
        self.reload(self.payment)
        self.assertEqual(self.payment.order.status, Order.Status.EXPIRED)
        self.assertEqual(self.stock_now(), stock)

    def test_customer_sees_the_new_status_and_no_refund_details(self):
        self.mark(self.payment)
        response = self.api_client(self.customer).get(
            reverse("payment-status", args=[self.order.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "REFUNDED")
        self.assertNotIn("refund", response.json())


class DuplicateAndInvalidTests(AdminRefundTestCase):
    def test_a_second_call_is_refused_and_creates_nothing(self):
        self.assertEqual(self.mark(self.payment).status_code, 200)
        response = self.mark(self.payment, gateway_reference="RF-2")

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())
        self.assertEqual(PaymentRefund.objects.count(), 1)
        self.assertEqual(
            AuditLog.objects.filter(action="payment.refund_confirmed").count(), 1
        )

    def test_a_refund_reference_cannot_be_used_twice(self):
        _customer, order, second = self.second_payment()
        self.pay_late(second, order)
        self.assertEqual(self.mark(self.payment).status_code, 200)

        response = self.mark(second, amount="50000.00")
        self.assertEqual(response.status_code, 400)
        self.assertIn("gateway_reference", response.json())
        self.reload(second)
        self.assertEqual(second.status, Payment.Status.REFUND_REQUIRED)
        self.assertEqual(PaymentRefund.objects.count(), 1)

    def test_only_a_payment_that_needs_a_refund_can_be_recorded(self):
        _customer, _order, pending = self.second_payment()
        customer3 = pt.make_user("customer3@test.com", User.Role.CUSTOMER)
        order3 = pt.make_order(customer3, self.product, 1)
        paid = start_payment(customer3, order3.pk, "pesapal")
        process_gateway_event(self.event(paid))

        for label, payment in (("pending", pending), ("paid", paid)):
            with self.subTest(status=label):
                response = self.mark(payment)
                self.assertEqual(response.status_code, 400)
                self.assertIn("status", response.json())
        self.assertEqual(PaymentRefund.objects.count(), 0)

    def test_an_amount_above_what_was_paid_is_refused(self):
        response = self.mark(self.payment, amount="100000.01")
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.json())
        self.assertEqual(PaymentRefund.objects.count(), 0)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)

    def test_bad_input_is_refused(self):
        cases = (
            {"amount": "0"},
            {"amount": "-5"},
            {"amount": "abc"},
            {"gateway_reference": ""},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.mark(self.payment, **overrides).status_code, 400)

        body = self.refund_body()
        del body["amount"]
        response = self.api_client(self.admin).post(
            reverse(MARK_URL, args=[self.payment.pk]), body, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PaymentRefund.objects.count(), 0)

    def test_unknown_payment_is_not_found(self):
        response = self.api_client(self.admin).post(
            reverse(MARK_URL, args=[999999]), self.refund_body(), format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_the_refund_can_reach_what_the_gateway_received(self):
        _customer, _order, payment = self.second_payment()
        process_gateway_event(
            self.event(
                payment,
                amount=Decimal("120000.00"),
                payload={"amount": "120000.00"},
            )
        )
        too_much = self.mark(payment, amount="120000.01")
        self.assertEqual(too_much.status_code, 400)

        response = self.mark(payment, amount="120000.00", gateway_reference="RF-9")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PaymentRefund.objects.get(payment=payment).amount, Decimal("120000.00")
        )
