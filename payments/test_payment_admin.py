from django.urls import reverse

from accounts.models import User
from payments import tests as pt
from payments.models import Payment


class PaymentAdminReadOnlyTests(pt.SandboxCase):
    """Payments change only through the payment code and the audited refund
    API, so the Django admin must not edit, add or delete them."""

    def setUp(self):
        super().setUp()
        self.superuser = pt.make_user("super@test.com", User.Role.ADMIN)
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()
        self.payment = Payment.objects.create(
            order=self.order,
            method="pesapal",
            amount=self.total,
            currency="UGX",
            status=Payment.Status.PENDING,
            gateway_reference="PAW-ADMIN-TEST",
        )
        self.client.force_login(self.superuser)

    def test_a_superuser_can_still_view_payments(self):
        response = self.client.get(reverse("admin:payments_payment_changelist"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse("admin:payments_payment_change", args=[self.payment.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_status_and_amount_cannot_be_changed_by_hand(self):
        url = reverse("admin:payments_payment_change", args=[self.payment.pk])
        self.client.post(
            url,
            {
                "order": self.order.pk,
                "method": "pesapal",
                "amount": "1.00",
                "currency": "USD",
                "status": Payment.Status.PAID,
                "gateway_reference": "PAW-ADMIN-TEST",
                "gateway_transaction_id": "",
                "payment_url": "",
                "failure_reason": "",
            },
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.payment.amount, self.total)
        self.assertEqual(self.payment.currency, "UGX")

    def test_payments_cannot_be_added_in_the_admin(self):
        url = reverse("admin:payments_payment_add")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(Payment.objects.count(), 1)

    def test_payments_cannot_be_deleted_in_the_admin(self):
        url = reverse("admin:payments_payment_delete", args=[self.payment.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())
