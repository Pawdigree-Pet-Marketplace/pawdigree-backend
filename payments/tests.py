from django.test import TestCase

"""Tests for the payments app, all in one file.Run everything that needs no internet and no real account: python manage.py test payments

Run one class or one test:
    python manage.py test payments.tests.ProcessGatewayEventTests
    python manage.py test payments.tests.PesapalWebhookEndToEndTests.test_completed_payment_marks_order_paid

What is in this file
1. FIXTURES : helpers that create users, a business, a product and an order.If they fail, fix them once here and every test benefits.
2. Fake gateway tests : the app's own logic, using the sandbox gateway.
3. Pesapal tests : the Pesapal gateway with Pesapal's servers faked. They run against both the sandbox URL and the live URL, but never  send a request to either.
4. Opt-in real tests : (skipped unless you switch them on) RUN_PESAPAL_SANDBOX_TESTS=1  calls Pesapal's real sandbox.  RUN_PESAPAL_LIVE_TESTS=1     asks the live API for a token only.
5. Smoke tests: (skipped unless you switch them on)PAYMENT_TEST_BASE_URL=...    sends real HTTP requests to a  running server, local or live. They only read.
"""

import json
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock, skipUnless

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from accounts.models import User
from businesses.models import Business
from cart.models import Cart, CartItem
from categories.models import Category
from orders.models import Order, VendorOrder
from orders.services import checkout, expire_overdue_orders
from products.models import Product

from .gateways import GatewayError, GatewayEvent
from .gateways.pesapal import PesapalGateway
from .gateways.sandbox import SandboxGateway
from .models import Payment
from .services import PaymentGatewayUnavailable, process_gateway_event, start_payment
from .views import SandboxPaymentSimulationView

# ---------------------------------------------------------------------------
# Settings used by the tests
# ---------------------------------------------------------------------------

SANDBOX_GATEWAY = "payments.gateways.sandbox.SandboxGateway"
PESAPAL_GATEWAY = "payments.gateways.pesapal.PesapalGateway"

PESAPAL_SANDBOX_URL = "https://cybqa.pesapal.com/pesapalv3/api"
PESAPAL_LIVE_URL = "https://pay.pesapal.com/v3/api"
PESAPAL_ENVIRONMENTS = (("sandbox", PESAPAL_SANDBOX_URL), ("live", PESAPAL_LIVE_URL),)

# Tests must not depend on the database cache table, so they use memory.
MEMORY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Django's test runner switches DEBUG off, and the sandbox gateway refuses to run without DEBUG, so the tests turn it back on. SECURE_SSL_REDIRECT is
# switched off so test requests are not redirected to https.
BASE_SETTINGS = dict(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    CACHES=MEMORY_CACHE,
    PAYMENT_METHODS=("pesapal",),
    PAYMENT_CURRENCY="UGX",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)

SANDBOX_SETTINGS = dict(
    BASE_SETTINGS,
    PAYMENT_GATEWAY_CLASS=SANDBOX_GATEWAY,
    SANDBOX_WEBHOOK_SECRET="test-secret",
    SANDBOX_PAYMENT_PAGE="http://frontend.test/sandbox-pay",
)

PESAPAL_SETTINGS = dict(
    BASE_SETTINGS,
    PAYMENT_GATEWAY_CLASS=PESAPAL_GATEWAY,
    PESAPAL_BASE_URL=PESAPAL_SANDBOX_URL,
    PESAPAL_CONSUMER_KEY="test-key",
    PESAPAL_CONSUMER_SECRET="test-secret",
    PESAPAL_IPN_ID="ipn-123",
    PESAPAL_CALLBACK_URL="https://frontend.test/payment/result/{order_id}",
    PESAPAL_CANCEL_URL="https://frontend.test/payment/cancelled",
)

# ---------------------------------------------------------------------------
# 1. FIXTURES
SHIPPING = dict(
    shipping_name="Test Customer",
    shipping_phone="0700000000",
    shipping_address="Plot 1, Test Road",
    shipping_city_district="Kampala",
    notes="",
)


def make_user(email, role):
    return User.objects.create_user(
        username=f"{role.lower()}-{email}",
        email=email,
        password="test-pass-123",
        role=role,
        first_name="Test",
        last_name="User",
    )


def make_business(vendor, name="Happy Paws"):
    return Business.objects.create(
        vendor=vendor,
        name=name,
        is_active=True,
        verification_status=Business.VerificationStatus.APPROVED,
        business_type=Business.BusinessType.PRODUCT_SELLER,
    )


def make_category(name="Accessories"):
    return Category.objects.create(
        name=name,
        kind=Category.Kind.MERCHANDISE,
        is_active=True,
    )


def make_order(customer, product, quantity=2):
    """Put the product in the customer's cart and run the real checkout."""
    cart, _ = Cart.objects.get_or_create(customer=customer)
    cart.items.all().delete()
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    return checkout(customer, dict(SHIPPING))


# ---------------------------------------------------------------------------
# A fake Pesapal, used by every Pesapal test
# ---------------------------------------------------------------------------

class FakeResponse:
    """Looks enough like a requests.Response for the gateway code."""

    def __init__(self, data=None, status_code=200, text=""):
        self._data = data
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("This reply has no JSON body.")
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakePesapal:
    """Stands in for Pesapal's servers and records every request it receives."""

    def __init__(
        self,
        state="Completed",
        amount="100000",
        currency="UGX",
        reference="PAW-0-test",
        tracking_id="track-123",
    ):
        self.state = state
        self.amount = amount
        self.currency = currency
        self.reference = reference
        self.tracking_id = tracking_id
        self.overrides = {}
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append(SimpleNamespace(method=method.upper(), url=url, kwargs=kwargs))

        for suffix, response in self.overrides.items():
            if suffix in url:
                return response

        if url.endswith("/Auth/RequestToken"):
            return FakeResponse(
                {
                    "token": "tok-1",
                    "expiryDate": "2026-11-17T09:00:00Z",
                    "error": None,
                    "status": "200",
                }
            )
        if url.endswith("/URLSetup/RegisterIPN"):
            return FakeResponse({"ipn_id": "ipn-123", "error": None, "status": "200"})
        if url.endswith("/Transactions/SubmitOrderRequest"):
            return FakeResponse(
                {
                    "order_tracking_id": self.tracking_id,
                    "merchant_reference": self.reference,
                    "redirect_url": "https://pesapal.test/pay/abc",
                    "error": None,
                    "status": "200",
                }
            )
        if "/Transactions/GetTransactionStatus" in url:
            return FakeResponse(
                {
                    "payment_method": "MtnMobileMoney",
                    "amount": float(self.amount),
                    "created_date": "2026-11-17T08:00:00Z",
                    "confirmation_code": "CONF123",
                    "payment_status_description": self.state,
                    "description": "Payment description from Pesapal",
                    "message": "Request processed successfully",
                    "payment_account": "0700****00",
                    "call_back_url": "https://frontend.test/payment/result/1",
                    "status_code": 1,
                    "merchant_reference": self.reference,
                    "payment_status_code": "",
                    "currency": self.currency,
                    # Pesapal sends an error object whose fields are all empty
                    # when nothing is wrong. The gateway must accept that.
                    "error": {
                        "error_type": None,
                        "code": None,
                        "message": None,
                        "call_back_url": None,
                    },
                    "status": "200",
                }
            )
        return FakeResponse({"error": "unexpected request"}, status_code=404)

    def calls_to(self, suffix):
        return [call for call in self.calls if suffix in call.url]


def patch_pesapal(fake):
    """Send every outgoing HTTP request of the Pesapal gateway to the fake."""
    return mock.patch("payments.gateways.pesapal.requests.request", side_effect=fake)


# ---------------------------------------------------------------------------
# Shared test case: a customer, a vendor with one product, and an order that is
# waiting for payment (50,000 x 2 = 100,000 UGX, stock 10 -> 8).
# ---------------------------------------------------------------------------


class PaymentTestCase(TestCase):
    price = Decimal("50000.00")
    stock = 10
    quantity = 2

    def setUp(self):
        cache.clear()
        self.vendor = make_user("vendor@test.com", User.Role.VENDOR)
        self.business = make_business(self.vendor)
        self.category = make_category()
        self.product = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Dog Leash",
            price=self.price,
            stock_quantity=self.stock,   # default is 0, and must be >= self.quantity
            is_active=True,
            approved=True,       # default is False, this is the likely culprit
        )
        self.customer = make_user("customer@test.com", User.Role.CUSTOMER)
        self.order = make_order(self.customer, self.product, self.quantity)
        self.total = self.price * self.quantity

    # -- small helpers ------------------------------------------------------

    def api_client(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def api_start(self, user, order_id=None, method="pesapal", **extra):
        if order_id is None:
            order_id = self.order.pk
        body = {"order_id": order_id, "method": method, **extra}
        return self.api_client(user).post(reverse("payment-start"), body, format="json")

    def stock_now(self):
        return Product.objects.get(pk=self.product.pk).stock_quantity

    def reload(self, payment):
        payment.refresh_from_db()
        payment.order.refresh_from_db()
        return payment

    def cart_count(self, customer=None):
        return CartItem.objects.filter(cart__customer=customer or self.customer).count()

    def expire_order(self, order=None):
        order = order or self.order
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        return expire_overdue_orders()

    def event(self, payment, **overrides):
        values = dict(
            reference=payment.gateway_reference,
            transaction_id=payment.gateway_transaction_id,
            succeeded=True,
            amount=payment.amount,
            currency=payment.currency,
            payload={"test": True},
            failure_reason="",
        )
        values.update(overrides)
        return GatewayEvent(**values)


@override_settings(**SANDBOX_SETTINGS)
class SandboxCase(PaymentTestCase):
    """Tests that use the fake (sandbox) gateway."""


@override_settings(**PESAPAL_SETTINGS)
class PesapalCase(PaymentTestCase):
    """Tests that use the Pesapal gateway, with Pesapal's servers faked."""


# ---------------------------------------------------------------------------
# 2. FAKE GATEWAY TESTS: the app's own logic
# ---------------------------------------------------------------------------

class PaymentMethodsApiTests(SandboxCase):
    def test_login_is_required(self):
        response = self.api_client().get(reverse("payment-methods"))
        self.assertEqual(response.status_code, 401)

    def test_lists_methods_and_currency(self):
        response = self.api_client(self.customer).get(reverse("payment-methods"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["methods"], ["pesapal"])
        self.assertEqual(response.data["currency"], "UGX")


class StartPaymentApiTests(SandboxCase):
    def test_creates_a_pending_payment(self):
        response = self.api_start(self.customer)

        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.currency, "UGX")
        self.assertEqual(payment.method, "pesapal")
        self.assertTrue(payment.gateway_reference.startswith(f"PAW-{self.order.pk}-"))
        self.assertIn(payment.gateway_reference, response.data["payment_url"])
        self.assertEqual(response.data["status"], "PENDING")

    def test_amount_comes_from_the_order_not_the_request(self):
        response = self.api_start(self.customer, amount=1)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.get(order=self.order).amount, self.total)

    def test_starting_twice_returns_the_same_payment(self):
        first = self.api_start(self.customer)
        second = self.api_start(self.customer)

        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Payment.objects.count(), 1)

    def test_login_is_required(self):
        response = self.api_start(None)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Payment.objects.count(), 0)

    def test_unsupported_method_is_refused(self):
        response = self.api_start(self.customer, method="visa")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_invalid_order_id_is_refused(self):
        response = self.api_start(self.customer, order_id=0)
        self.assertEqual(response.status_code, 400)

    def test_cannot_pay_for_another_customers_order(self):
        other = make_user("other@test.com", User.Role.CUSTOMER)
        response = self.api_start(other)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Payment.objects.count(), 0)

    def test_unknown_order_is_not_found(self):
        response = self.api_start(self.customer, order_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_vendors_cannot_start_payments(self):
        response = self.api_start(self.vendor)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)

    def test_order_that_is_not_waiting_for_payment_is_refused(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.CANCELLED)
        response = self.api_start(self.customer)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_expired_order_is_refused_and_stock_comes_back(self):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = self.api_start(self.customer)

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.EXPIRED)
        self.assertEqual(self.stock_now(), self.stock)

    def test_gateway_failure_leaves_no_payment_behind(self):
        with mock.patch("payments.services.get_gateway") as get_gateway:
            get_gateway.return_value.create_payment.side_effect = GatewayError("down")
            response = self.api_start(self.customer)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(Payment.objects.count(), 0)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_PAYMENT)


class PaymentStatusApiTests(SandboxCase):
    def test_shows_the_customers_own_payment(self):
        self.api_start(self.customer)
        response = self.api_client(self.customer).get(
            reverse("payment-status", args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["order_status"], Order.Status.PENDING_PAYMENT)
        self.assertIsNotNone(response.data["order_expires_at"])
        self.assertEqual(Decimal(response.data["amount"]), self.total)

    def test_hides_internal_fields(self):
        self.api_start(self.customer)
        response = self.api_client(self.customer).get(
            reverse("payment-status", args=[self.order.pk])
        )
        for field in ("gateway_payload", "gateway_transaction_id", "failure_reason"):
            self.assertNotIn(field, response.data)

    def test_another_customer_cannot_see_it(self):
        self.api_start(self.customer)
        other = make_user("other@test.com", User.Role.CUSTOMER)
        response = self.api_client(other).get(
            reverse("payment-status", args=[self.order.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_not_found_before_a_payment_is_started(self):
        response = self.api_client(self.customer).get(
            reverse("payment-status", args=[self.order.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_login_is_required(self):
        response = self.api_client().get(reverse("payment-status", args=[self.order.pk]))
        self.assertEqual(response.status_code, 401)

    def test_status_follows_the_payment_result(self):
        payment = start_payment(self.customer, self.order.pk, "pesapal")
        process_gateway_event(self.event(payment))

        response = self.api_client(self.customer).get(
            reverse("payment-status", args=[self.order.pk])
        )
        self.assertEqual(response.data["status"], "PAID")
        self.assertEqual(response.data["order_status"], Order.Status.PAID)
        self.assertIsNotNone(response.data["paid_at"])


class ProcessGatewayEventTests(SandboxCase):
    """What happens to the payment, order, stock and cart for each result."""

    def setUp(self):
        super().setUp()
        self.payment = start_payment(self.customer, self.order.pk, "pesapal")

    def test_success_marks_payment_and_order_paid(self):
        process_gateway_event(self.event(self.payment))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertIsNotNone(self.payment.paid_at)
        self.assertEqual(self.payment.order.status, Order.Status.PAID)
        statuses = set(self.order.vendor_orders.values_list("status", flat=True))
        self.assertEqual(statuses, {VendorOrder.Status.PAID})

    def test_success_empties_the_cart_but_keeps_the_stock_taken(self):
        self.assertEqual(self.cart_count(), 1)
        process_gateway_event(self.event(self.payment))

        self.assertEqual(self.cart_count(), 0)
        self.assertEqual(self.stock_now(), self.stock - self.quantity)

    def test_success_with_a_whole_number_amount_is_accepted(self):
        # Gateways often send 100000 where the order says 100000.00.
        process_gateway_event(self.event(self.payment, amount=Decimal("100000")))
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_failure_cancels_the_order_and_restores_stock(self):
        process_gateway_event(
            self.event(self.payment, succeeded=False, failure_reason="Insufficient funds")
        )

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.payment.failure_reason, "Insufficient funds")
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock_now(), self.stock)
        self.assertEqual(self.cart_count(), 1)  # the customer can try again

    def test_the_same_success_twice_changes_nothing(self):
        process_gateway_event(self.event(self.payment))
        self.reload(self.payment)
        paid_at = self.payment.paid_at

        process_gateway_event(self.event(self.payment))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.payment.paid_at, paid_at)
        self.assertEqual(self.stock_now(), self.stock - self.quantity)

    def test_the_same_failure_twice_restores_stock_only_once(self):
        failed = self.event(self.payment, succeeded=False, failure_reason="Declined")
        process_gateway_event(failed)
        process_gateway_event(failed)

        self.assertEqual(self.stock_now(), self.stock)

    def test_a_failure_after_success_is_ignored(self):
        process_gateway_event(self.event(self.payment))
        process_gateway_event(self.event(self.payment, succeeded=False))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.payment.order.status, Order.Status.PAID)

    def test_wrong_amount_needs_a_refund_and_cancels_the_order(self):
        process_gateway_event(self.event(self.payment, amount=Decimal("1.00")))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)
        self.assertIn("amount", self.payment.failure_reason)
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock_now(), self.stock)

    def test_wrong_currency_needs_a_refund(self):
        process_gateway_event(self.event(self.payment, currency="USD"))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)

    def test_payment_after_the_order_expired_needs_a_refund(self):
        self.assertEqual(self.expire_order(), 1)
        self.assertEqual(self.stock_now(), self.stock)

        process_gateway_event(self.event(self.payment))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)
        self.assertIn("after the order", self.payment.failure_reason)
        self.assertEqual(self.payment.order.status, Order.Status.EXPIRED)
        self.assertEqual(self.stock_now(), self.stock)  # not given back twice

    def test_payment_after_the_order_was_cancelled_needs_a_refund(self):
        # Starting a new checkout cancels the customer's old unpaid order.
        make_order(self.customer, self.product, 1)

        process_gateway_event(self.event(self.payment))

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)

    def test_unknown_reference_is_not_found(self):
        with self.assertRaises(NotFound):
            process_gateway_event(self.event(self.payment, reference="PAW-0-nothing"))

    def test_gateway_data_is_kept_for_support(self):
        process_gateway_event(self.event(self.payment, payload={"confirmation_code": "X1"}))
        self.reload(self.payment)
        self.assertEqual(self.payment.gateway_payload, {"confirmation_code": "X1"})


class SandboxGatewayTests(SandboxCase):
    """The fake gateway and its signed webhook."""

    def setUp(self):
        super().setUp()
        self.payment = start_payment(self.customer, self.order.pk, "pesapal")

    def webhook_body(self, **overrides):
        body = {
            "reference": self.payment.gateway_reference,
            "transaction_id": self.payment.gateway_transaction_id,
            "status": "success",
            "amount": str(self.payment.amount),
            "currency": self.payment.currency,
            "reason": "",
        }
        body.update(overrides)
        return body

    def post_webhook(self, body, signature=None):
        raw = body if isinstance(body, str) else json.dumps(body)
        if signature is None:
            signature = SandboxGateway.sign(raw.encode())
        return self.client.post(
            reverse("payment-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

    def test_payment_link_points_at_the_sandbox_page(self):
        self.assertTrue(self.payment.payment_url.startswith("http://frontend.test/sandbox-pay"))
        self.assertIn(f"reference={self.payment.gateway_reference}", self.payment.payment_url)
        self.assertIn(f"order_id={self.order.pk}", self.payment.payment_url)
        self.assertEqual(
            self.payment.gateway_transaction_id, f"SBX-{self.payment.gateway_reference}"
        )

    def test_signed_success_marks_the_order_paid(self):
        response = self.post_webhook(self.webhook_body())

        self.assertEqual(response.status_code, 200)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.payment.order.status, Order.Status.PAID)

    def test_signed_failure_cancels_the_order(self):
        response = self.post_webhook(self.webhook_body(status="failed", reason="No funds"))

        self.assertEqual(response.status_code, 200)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock_now(), self.stock)

    def test_wrong_signature_is_refused_and_nothing_changes(self):
        response = self.post_webhook(self.webhook_body(), signature="not-the-signature")

        self.assertEqual(response.status_code, 400)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_missing_signature_is_refused(self):
        response = self.client.post(
            reverse("payment-webhook"),
            data=json.dumps(self.webhook_body()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_a_body_changed_after_signing_is_refused(self):
        signature = SandboxGateway.sign(json.dumps(self.webhook_body()).encode())
        tampered = self.webhook_body(amount="1.00")

        response = self.post_webhook(tampered, signature=signature)

        self.assertEqual(response.status_code, 400)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_signed_but_malformed_body_is_refused(self):
        self.assertEqual(self.post_webhook("this is not json").status_code, 400)
        self.assertEqual(self.post_webhook('{"status": "success"}').status_code, 400)

    def test_unknown_reference_is_404(self):
        response = self.post_webhook(self.webhook_body(reference="PAW-0-nothing"))
        self.assertEqual(response.status_code, 404)

    def test_the_same_webhook_twice_is_harmless(self):
        self.post_webhook(self.webhook_body())
        response = self.post_webhook(self.webhook_body())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stock_now(), self.stock - self.quantity)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_a_signed_payment_of_the_wrong_amount_needs_a_refund(self):
        self.post_webhook(self.webhook_body(amount="5.00"))
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)

    def test_webhook_does_not_accept_get(self):
        response = self.client.get(reverse("payment-webhook"))
        self.assertEqual(response.status_code, 405)

    def test_sandbox_gateway_refuses_to_run_without_debug(self):
        with self.settings(DEBUG=False):
            with self.assertRaises(ImproperlyConfigured):
                SandboxGateway()


class SandboxSimulationViewTests(SandboxCase):
    """The development endpoint that lets a customer "pay" without a gateway.

    The view is called directly, because the URL is only registered when the
    server starts with DEBUG on, and the test runner starts with DEBUG off.
    """

    def setUp(self):
        super().setUp()
        self.payment = start_payment(self.customer, self.order.pk, "pesapal")

    def simulate(self, user, data):
        request = APIRequestFactory().post("/sandbox/simulate/", data, format="json")
        force_authenticate(request, user=user)
        return SandboxPaymentSimulationView.as_view()(request)

    def test_success_pays_the_order(self):
        response = self.simulate(
            self.customer, {"reference": self.payment.gateway_reference, "result": "success"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "PAID")
        self.reload(self.payment)
        self.assertEqual(self.payment.order.status, Order.Status.PAID)

    def test_failure_cancels_the_order(self):
        response = self.simulate(
            self.customer, {"reference": self.payment.gateway_reference, "result": "failed"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "FAILED")
        self.assertEqual(self.stock_now(), self.stock)

    def test_cannot_simulate_someone_elses_payment(self):
        other = make_user("other@test.com", User.Role.CUSTOMER)
        response = self.simulate(
            other, {"reference": self.payment.gateway_reference, "result": "success"}
        )
        self.assertEqual(response.status_code, 404)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_vendors_cannot_simulate(self):
        response = self.simulate(
            self.vendor, {"reference": self.payment.gateway_reference, "result": "success"}
        )
        self.assertEqual(response.status_code, 403)

    def test_a_processed_payment_cannot_be_simulated_again(self):
        data = {"reference": self.payment.gateway_reference, "result": "success"}
        self.simulate(self.customer, data)
        response = self.simulate(self.customer, data)
        self.assertEqual(response.status_code, 400)

    def test_invalid_result_is_refused(self):
        response = self.simulate(
            self.customer, {"reference": self.payment.gateway_reference, "result": "maybe"}
        )
        self.assertEqual(response.status_code, 400)

    def test_does_not_exist_when_the_gateway_is_not_the_sandbox(self):
        data = {"reference": self.payment.gateway_reference, "result": "success"}
        with self.settings(PAYMENT_GATEWAY_CLASS=PESAPAL_GATEWAY):
            response = self.simulate(self.customer, data)
        self.assertEqual(response.status_code, 404)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_does_not_exist_when_debug_is_off(self):
        data = {"reference": self.payment.gateway_reference, "result": "success"}
        with self.settings(DEBUG=False):
            response = self.simulate(self.customer, data)
        self.assertEqual(response.status_code, 404)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)


# ---------------------------------------------------------------------------
# 3. PESAPAL TESTS: the Pesapal gateway, with Pesapal's servers faked
# ---------------------------------------------------------------------------


class PesapalGatewayTests(PesapalCase):
    def webhook_request(self, raw=None, query=""):
        if raw is None:
            raw = json.dumps(
                {
                    "OrderTrackingId": "track-123",
                    "OrderNotificationType": "IPNCHANGE",
                    "OrderMerchantReference": "PAW-1-abc",
                }
            )
        return RequestFactory().post("/webhook/" + query, data=raw, content_type="application/json")

    # -- connection and settings -------------------------------------------

    def test_token_is_requested_once_and_then_cached(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            gateway = PesapalGateway()
            self.assertEqual(gateway._token(), "tok-1")
            self.assertEqual(gateway._token(), "tok-1")
            self.assertEqual(PesapalGateway()._token(), "tok-1")

        requests_made = fake.calls_to("/Auth/RequestToken")
        self.assertEqual(len(requests_made), 1)
        self.assertEqual(
            requests_made[0].kwargs["json"],
            {"consumer_key": "test-key", "consumer_secret": "test-secret"},
        )

    def test_missing_credentials_stop_the_gateway_from_starting(self):
        for name in ("PESAPAL_BASE_URL", "PESAPAL_CONSUMER_KEY", "PESAPAL_CONSUMER_SECRET"):
            with self.subTest(setting=name), self.settings(**{name: ""}):
                with self.assertRaises(ImproperlyConfigured):
                    PesapalGateway()

    def test_a_missing_ipn_id_is_a_configuration_error(self):
        with patch_pesapal(FakePesapal()), self.settings(PESAPAL_IPN_ID=""):
            with self.assertRaises(ImproperlyConfigured):
                start_payment(self.customer, self.order.pk, "pesapal")
        self.assertEqual(Payment.objects.count(), 0)

    def test_trailing_slash_in_the_base_url_is_harmless(self):
        fake = FakePesapal()
        with patch_pesapal(fake), self.settings(PESAPAL_BASE_URL=PESAPAL_SANDBOX_URL + "/"):
            PesapalGateway()._token()
        self.assertEqual(fake.calls[0].url, PESAPAL_SANDBOX_URL + "/Auth/RequestToken")

    # -- failures from Pesapal ----------------------------------------------

    def test_rejected_credentials_raise_a_gateway_error(self):
        fake = FakePesapal()
        fake.overrides["/Auth/RequestToken"] = FakeResponse({"error": "bad"}, 401, "denied")
        with patch_pesapal(fake):
            with self.assertRaises(GatewayError):
                PesapalGateway()._token()

    def test_a_reply_without_a_token_raises_a_gateway_error(self):
        fake = FakePesapal()
        fake.overrides["/Auth/RequestToken"] = FakeResponse({"error": None})
        with patch_pesapal(fake):
            with self.assertRaises(GatewayError):
                PesapalGateway()._token()

    def test_a_reply_that_is_not_json_raises_a_gateway_error(self):
        fake = FakePesapal()
        fake.overrides["/Auth/RequestToken"] = FakeResponse(None, 200, "<html>oops</html>")
        with patch_pesapal(fake):
            with self.assertRaises(GatewayError):
                PesapalGateway()._token()

    def test_a_network_failure_raises_a_gateway_error(self):
        with mock.patch(
            "payments.gateways.pesapal.requests.request",
            side_effect=requests.ConnectionError("no network"),
        ):
            with self.assertRaises(GatewayError):
                PesapalGateway()._token()

    def test_a_timeout_raises_a_gateway_error(self):
        with mock.patch(
            "payments.gateways.pesapal.requests.request",
            side_effect=requests.Timeout("too slow"),
        ):
            with self.assertRaises(GatewayError):
                PesapalGateway()._token()

    def test_every_request_has_a_timeout(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            PesapalGateway()._token()
        self.assertTrue(fake.calls[0].kwargs["timeout"] > 0)

    # -- registering the webhook ---------------------------------------------

    def test_register_ipn_sends_the_url_and_returns_the_id(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            ipn_id = PesapalGateway().register_ipn("https://example.test/api/payments/webhook/")

        self.assertEqual(ipn_id, "ipn-123")
        sent = fake.calls_to("/URLSetup/RegisterIPN")[0]
        self.assertEqual(
            sent.kwargs["json"],
            {
                "url": "https://example.test/api/payments/webhook/",
                "ipn_notification_type": "POST",
            },
        )
        self.assertEqual(sent.kwargs["headers"]["Authorization"], "Bearer tok-1")

    # -- starting a payment ----------------------------------------------------

    def test_the_order_sent_to_pesapal_is_correct(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            payment = start_payment(self.customer, self.order.pk, "pesapal")

        sent = fake.calls_to("/Transactions/SubmitOrderRequest")[0]
        payload = sent.kwargs["json"]

        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.kwargs["headers"]["Authorization"], "Bearer tok-1")
        self.assertEqual(payload["id"], payment.gateway_reference)
        self.assertEqual(payload["currency"], "UGX")
        self.assertEqual(payload["amount"], float(self.total))  # no surcharge added
        self.assertEqual(payload["notification_id"], "ipn-123")
        self.assertEqual(
            payload["callback_url"], f"https://frontend.test/payment/result/{self.order.pk}"
        )
        self.assertEqual(payload["cancellation_url"], "https://frontend.test/payment/cancelled")
        self.assertLessEqual(len(payload["description"]), 100)
        self.assertEqual(payload["billing_address"]["email_address"], self.customer.email)
        self.assertEqual(payload["billing_address"]["phone_number"], self.order.shipping_phone)
        self.assertEqual(payload["billing_address"]["first_name"], self.customer.first_name)

    def test_the_tracking_id_and_link_are_saved(self):
        with patch_pesapal(FakePesapal(tracking_id="track-999")):
            payment = start_payment(self.customer, self.order.pk, "pesapal")

        self.assertEqual(payment.gateway_transaction_id, "track-999")
        self.assertEqual(payment.payment_url, "https://pesapal.test/pay/abc")
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_the_cancellation_url_is_left_out_when_not_configured(self):
        fake = FakePesapal()
        with patch_pesapal(fake), self.settings(PESAPAL_CANCEL_URL=""):
            start_payment(self.customer, self.order.pk, "pesapal")
        payload = fake.calls_to("/Transactions/SubmitOrderRequest")[0].kwargs["json"]
        self.assertNotIn("cancellation_url", payload)

    def test_an_error_from_pesapal_leaves_no_payment_behind(self):
        fake = FakePesapal()
        fake.overrides["/Transactions/SubmitOrderRequest"] = FakeResponse(
            {
                "error": {"error_type": "api_error", "code": "invalid_data", "message": "Bad"},
                "status": "500",
            }
        )
        with patch_pesapal(fake):
            with self.assertRaises(PaymentGatewayUnavailable):
                start_payment(self.customer, self.order.pk, "pesapal")

        self.assertEqual(Payment.objects.count(), 0)

    def test_a_reply_without_a_payment_link_is_an_error(self):
        fake = FakePesapal()
        fake.overrides["/Transactions/SubmitOrderRequest"] = FakeResponse(
            {"order_tracking_id": "track-123", "error": None}
        )
        with patch_pesapal(fake):
            with self.assertRaises(PaymentGatewayUnavailable):
                start_payment(self.customer, self.order.pk, "pesapal")
        self.assertEqual(Payment.objects.count(), 0)

    def test_starting_twice_calls_pesapal_only_once(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            first = start_payment(self.customer, self.order.pk, "pesapal")
            second = start_payment(self.customer, self.order.pk, "pesapal")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(len(fake.calls_to("/Transactions/SubmitOrderRequest")), 1)

    # -- reading a notification --------------------------------------------------

    def test_completed_payment_becomes_a_successful_event(self):
        fake = FakePesapal(state="Completed", amount="100000", reference="PAW-7-abcd")
        with patch_pesapal(fake):
            event = PesapalGateway().read_webhook(self.webhook_request())

        self.assertTrue(event.succeeded)
        self.assertEqual(event.reference, "PAW-7-abcd")  # taken from Pesapal's answer
        self.assertEqual(event.transaction_id, "track-123")
        self.assertEqual(event.amount, Decimal("100000"))
        self.assertEqual(event.currency, "UGX")
        self.assertEqual(event.payload["confirmation_code"], "CONF123")
        self.assertEqual(event.failure_reason, "")

    def test_failed_invalid_and_reversed_payments_become_failed_events(self):
        for state in ("Failed", "Invalid", "Reversed", "FAILED"):
            with self.subTest(state=state):
                cache.clear()
                with patch_pesapal(FakePesapal(state=state)):
                    event = PesapalGateway().read_webhook(self.webhook_request())
                self.assertFalse(event.succeeded)
                self.assertTrue(event.failure_reason)

    def test_a_payment_that_is_not_final_is_not_acted_on(self):
        for state in ("Pending", "", "Something new"):
            with self.subTest(state=state):
                cache.clear()
                with patch_pesapal(FakePesapal(state=state)):
                    with self.assertRaises(GatewayError):
                        PesapalGateway().read_webhook(self.webhook_request())

    def test_the_status_is_always_asked_of_pesapal(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            PesapalGateway().read_webhook(self.webhook_request())

        asked = fake.calls_to("/Transactions/GetTransactionStatus")[0]
        self.assertEqual(asked.method, "GET")
        self.assertEqual(asked.kwargs["params"], {"orderTrackingId": "track-123"})

    def test_a_notification_without_a_tracking_id_never_reaches_pesapal(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            with self.assertRaises(GatewayError):
                PesapalGateway().read_webhook(self.webhook_request(raw="{}"))
        self.assertEqual(fake.calls, [])

    def test_a_body_that_is_not_a_json_object_is_refused(self):
        for raw in ("not json", "[1, 2]", '"text"'):
            with self.subTest(raw=raw):
                with patch_pesapal(FakePesapal()):
                    with self.assertRaises(GatewayError):
                        PesapalGateway().read_webhook(self.webhook_request(raw=raw))

    def test_the_tracking_id_can_arrive_in_the_url(self):
        fake = FakePesapal()
        with patch_pesapal(fake):
            event = PesapalGateway().read_webhook(
                self.webhook_request(raw="{}", query="?OrderTrackingId=track-from-url")
            )
        asked = fake.calls_to("/Transactions/GetTransactionStatus")[0]
        self.assertEqual(asked.kwargs["params"], {"orderTrackingId": "track-from-url"})
        self.assertEqual(event.transaction_id, "track-from-url")

    def test_a_forged_notification_is_refused(self):
        fake = FakePesapal()
        fake.overrides["/Transactions/GetTransactionStatus"] = FakeResponse(
            {"error": {"code": "not_found", "message": "No such order"}}, 404
        )
        with patch_pesapal(fake):
            with self.assertRaises(GatewayError):
                PesapalGateway().read_webhook(self.webhook_request())

    def test_an_unexpected_status_reply_is_refused(self):
        fake = FakePesapal()
        fake.overrides["/Transactions/GetTransactionStatus"] = FakeResponse(
            {"payment_status_description": "Completed", "error": None}
        )
        with patch_pesapal(fake):
            with self.assertRaises(GatewayError):
                PesapalGateway().read_webhook(self.webhook_request())

    def test_acknowledgement_has_the_shape_pesapal_expects(self):
        event = self.event(
            Payment(gateway_reference="PAW-7-abcd", gateway_transaction_id="track-123",
                    amount=Decimal("1"), currency="UGX")
        )
        self.assertEqual(
            PesapalGateway().acknowledgement(event),
            {
                "orderNotificationType": "IPNCHANGE",
                "orderTrackingId": "track-123",
                "orderMerchantReference": "PAW-7-abcd",
                "status": 200,
            },
        )

    # -- the same flow on Pesapal's sandbox URL and its live URL ---------------

    def test_full_flow_on_the_sandbox_and_live_urls(self):
        """Every request must go to the configured Pesapal address, and the
        payment must complete the same way on both. Nothing is really sent."""
        for index, (name, base_url) in enumerate(PESAPAL_ENVIRONMENTS):
            with self.subTest(environment=name), self.settings(PESAPAL_BASE_URL=base_url):
                cache.clear()
                customer = make_user(f"env{index}@test.com", User.Role.CUSTOMER)
                order = make_order(customer, self.product)
                fake = FakePesapal()

                with patch_pesapal(fake):
                    payment = start_payment(customer, order.pk, "pesapal")
                    fake.reference = payment.gateway_reference
                    fake.amount = payment.amount
                    response = self.client.post(
                        reverse("payment-webhook"),
                        data=json.dumps({"OrderTrackingId": "track-123"}),
                        content_type="application/json",
                    )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(fake.calls)
                for call in fake.calls:
                    self.assertTrue(
                        call.url.startswith(base_url),
                        f"{call.url} is not under {base_url}",
                    )
                self.reload(payment)
                self.assertEqual(payment.status, Payment.Status.PAID)
                self.assertEqual(payment.order.status, Order.Status.PAID)

    def test_the_tokens_of_two_environments_are_not_mixed_up(self):
        """The token cache is shared, so a sandbox token must not be reused
        against the live API. This documents the current behaviour: if it
        fails, the cache key needs the base URL in it."""
        fake = FakePesapal()
        with patch_pesapal(fake):
            PesapalGateway()._token()
            with self.settings(PESAPAL_BASE_URL=PESAPAL_LIVE_URL):
                PesapalGateway()._token()

        self.assertEqual(
            len(fake.calls_to("/Auth/RequestToken")),
            2,
            "A token fetched from one Pesapal environment was reused for another.",
        )


class PesapalWebhookEndToEndTests(PesapalCase):
    """Customer starts a payment, then Pesapal's notification arrives."""

    def setUp(self):
        super().setUp()
        self.fake = FakePesapal()
        with patch_pesapal(self.fake):
            self.payment = start_payment(self.customer, self.order.pk, "pesapal")
        self.fake.reference = self.payment.gateway_reference
        self.fake.amount = self.payment.amount

    def notify(self, **extra):
        body = {
            "OrderTrackingId": "track-123",
            "OrderNotificationType": "IPNCHANGE",
            "OrderMerchantReference": self.payment.gateway_reference,
            **extra,
        }
        with patch_pesapal(self.fake):
            return self.client.post(
                reverse("payment-webhook"),
                data=json.dumps(body),
                content_type="application/json",
            )

    def test_completed_payment_marks_order_paid(self):
        response = self.notify()

        self.assertEqual(response.status_code, 200)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.payment.order.status, Order.Status.PAID)
        self.assertEqual(self.cart_count(), 0)

    def test_pesapal_gets_the_acknowledgement_it_expects(self):
        body = self.notify().json()

        self.assertEqual(body["orderNotificationType"], "IPNCHANGE")
        self.assertEqual(body["orderTrackingId"], "track-123")
        self.assertEqual(body["orderMerchantReference"], self.payment.gateway_reference)
        self.assertEqual(body["status"], 200)

    def test_no_login_is_needed_for_the_notification(self):
        # self.client is not logged in, and the notification still works.
        self.assertEqual(self.notify().status_code, 200)

    def test_confirmation_code_is_kept_for_refunds(self):
        self.notify()
        self.reload(self.payment)
        self.assertEqual(self.payment.gateway_payload["confirmation_code"], "CONF123")
        self.assertEqual(self.payment.gateway_transaction_id, "track-123")

    def test_failed_payment_cancels_the_order_and_restores_stock(self):
        self.fake.state = "Failed"
        response = self.notify()

        self.assertEqual(response.status_code, 200)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock_now(), self.stock)

    def test_the_same_notification_twice_is_harmless(self):
        self.notify()
        response = self.notify()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stock_now(), self.stock - self.quantity)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_a_forged_notification_changes_nothing(self):
        self.fake.overrides["/Transactions/GetTransactionStatus"] = FakeResponse(
            {"error": {"code": "not_found"}}, 404
        )
        response = self.notify(OrderTrackingId="made-up")

        self.assertEqual(response.status_code, 400)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_a_notification_cannot_pay_with_the_wrong_amount(self):
        self.fake.amount = "5"
        self.notify()

        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)
        self.assertEqual(self.payment.order.status, Order.Status.CANCELLED)

    def test_a_late_payment_is_flagged_for_refund(self):
        self.expire_order()
        response = self.notify()

        self.assertEqual(response.status_code, 200)  # so Pesapal stops retrying
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.REFUND_REQUIRED)
        self.assertEqual(self.payment.order.status, Order.Status.EXPIRED)

    def test_a_notification_for_an_unknown_payment_is_404(self):
        self.fake.reference = "PAW-0-unknown"
        self.assertEqual(self.notify().status_code, 404)

    def test_a_payment_that_is_still_pending_at_pesapal_is_left_alone(self):
        self.fake.state = "Pending"
        response = self.notify()

        self.assertEqual(response.status_code, 400)
        self.reload(self.payment)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.payment.order.status, Order.Status.PENDING_PAYMENT)


# ---------------------------------------------------------------------------
# 4. OPT-IN TESTS THAT TALK TO THE REAL PESAPAL
#
# They are skipped unless you switch them on, because they need internet and
# real credentials. Neither class ever pays for anything.
# ---------------------------------------------------------------------------


@skipUnless(
    os.environ.get("RUN_PESAPAL_SANDBOX_TESTS") == "1",
    "Set RUN_PESAPAL_SANDBOX_TESTS=1 to call Pesapal's real sandbox.",
)
@override_settings(CACHES=MEMORY_CACHE)
class PesapalRealSandboxTests(SimpleTestCase):
    """Uses your real PESAPAL_* settings, and only if they point at the sandbox.

        RUN_PESAPAL_SANDBOX_TESTS=1 python manage.py test payments.tests.PesapalRealSandboxTests
    """

    def setUp(self):
        if "cybqa.pesapal.com" not in settings.PESAPAL_BASE_URL:
            self.skipTest("PESAPAL_BASE_URL is not Pesapal's sandbox. Refusing to run.")
        if not (settings.PESAPAL_CONSUMER_KEY and settings.PESAPAL_CONSUMER_SECRET):
            self.skipTest("PESAPAL_CONSUMER_KEY / PESAPAL_CONSUMER_SECRET are not set.")

    def test_the_sandbox_gives_a_token(self):
        self.assertTrue(PesapalGateway()._token())

    def test_the_sandbox_gives_a_checkout_link(self):
        if not settings.PESAPAL_IPN_ID:
            self.skipTest("PESAPAL_IPN_ID is not set. Run register_pesapal_ipn first.")

        payment = SimpleNamespace(
            gateway_reference=f"TEST-{uuid.uuid4().hex[:12]}",
            currency="UGX",
            amount=Decimal("1000.00"),
        )
        order = SimpleNamespace(
            pk=0,
            shipping_phone="0700000000",
            customer=SimpleNamespace(
                email="test@example.com", first_name="Test", last_name="User"
            ),
        )

        result = PesapalGateway().create_payment(payment, order)

        self.assertTrue(result.transaction_id)
        self.assertTrue(result.payment_url.startswith("https://"))

    def test_a_forged_tracking_id_cannot_pay_anything(self):
        # A forged notification names an id Pesapal does not know. Either the
        # gateway refuses it, or it returns an event with no payment reference,
        # which the payment code answers with "not found". Both are safe.
        request = RequestFactory().post(
            "/webhook/",
            data=json.dumps({"OrderTrackingId": "00000000-0000-0000-0000-000000000000"}),
            content_type="application/json",
        )
        try:
            event = PesapalGateway().read_webhook(request)
        except GatewayError:
            return
        self.assertFalse(event.reference)


@skipUnless(
    os.environ.get("RUN_PESAPAL_LIVE_TESTS") == "1",
    "Set RUN_PESAPAL_LIVE_TESTS=1 (and the PESAPAL_LIVE_* variables) to check live credentials.",
)
@override_settings(CACHES=MEMORY_CACHE)
class PesapalLiveReadOnlyTests(SimpleTestCase):
    """Asks the live Pesapal API for a token and nothing else.

    It never creates an order, never registers a webhook and never moves
    money. It only proves the live key, secret and URL are accepted.

        PESAPAL_LIVE_CONSUMER_KEY=...  PESAPAL_LIVE_CONSUMER_SECRET=...
        RUN_PESAPAL_LIVE_TESTS=1 python manage.py test payments.tests.PesapalLiveReadOnlyTests
    """

    def test_live_credentials_are_accepted(self):
        key = os.environ.get("PESAPAL_LIVE_CONSUMER_KEY", "")
        secret = os.environ.get("PESAPAL_LIVE_CONSUMER_SECRET", "")
        base_url = os.environ.get("PESAPAL_LIVE_BASE_URL", PESAPAL_LIVE_URL)
        if not (key and secret):
            self.skipTest("PESAPAL_LIVE_CONSUMER_KEY / PESAPAL_LIVE_CONSUMER_SECRET are not set.")

        with self.settings(
            PESAPAL_BASE_URL=base_url,
            PESAPAL_CONSUMER_KEY=key,
            PESAPAL_CONSUMER_SECRET=secret,
        ):
            token = PesapalGateway()._token()

        self.assertTrue(token)


# ---------------------------------------------------------------------------
# 5. SMOKE TESTS AGAINST A RUNNING SERVER (local or live)
#
# These send real HTTP requests to a server that is already running. They only
# read: they create no orders, no payments and no accounts. They are skipped
# unless PAYMENT_TEST_BASE_URL is set.
#
#   Local server:
#     PAYMENT_TEST_BASE_URL=http://localhost:8000 \
#         python manage.py test payments.tests.RunningServerSmokeTests
#
#   Live server (use https, and add IS_LIVE so the extra live checks run):
#     PAYMENT_TEST_BASE_URL=https://your-live-domain PAYMENT_TEST_IS_LIVE=1 \
#         python manage.py test payments.tests.RunningServerSmokeTests
#
#   Optional: PAYMENT_TEST_AUTH_HEADER="Bearer <a CUSTOMER's token>" turns on the
#   logged-in checks. PAYMENT_TEST_PREFIX changes the URL prefix (default
#   "api/payments").
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("PAYMENT_TEST_BASE_URL", "").rstrip("/")
API_PREFIX = os.environ.get("PAYMENT_TEST_PREFIX", "api/payments").strip("/")
AUTH_HEADER = os.environ.get("PAYMENT_TEST_AUTH_HEADER", "")
IS_LIVE = os.environ.get("PAYMENT_TEST_IS_LIVE") == "1"


@skipUnless(API_BASE, "Set PAYMENT_TEST_BASE_URL to test a running server.")
class RunningServerSmokeTests(SimpleTestCase):
    def call(self, method, path, authenticated=False, **kwargs):
        headers = {"Authorization": AUTH_HEADER} if authenticated else {}
        return requests.request(
            method,
            f"{API_BASE}/{API_PREFIX}/{path}",
            headers=headers,
            timeout=20,
            allow_redirects=False,  # a redirect is a result worth seeing, not hiding
            **kwargs,
        )

    def need_login_token(self):
        if not AUTH_HEADER:
            self.skipTest("Set PAYMENT_TEST_AUTH_HEADER to run the logged-in checks.")

    # -- no login needed to run these ----------------------------------------

    def test_methods_need_a_login(self):
        self.assertEqual(self.call("GET", "methods/").status_code, 401)

    def test_starting_a_payment_needs_a_login(self):
        response = self.call("POST", "start/", json={"order_id": 1, "method": "pesapal"})
        self.assertEqual(response.status_code, 401)

    def test_payment_status_needs_a_login(self):
        self.assertEqual(self.call("GET", "orders/1/").status_code, 401)

    def test_the_webhook_refuses_an_empty_notification(self):
        response = self.call("POST", "webhook/", json={})
        self.assertEqual(response.status_code, 400)

    def test_the_webhook_refuses_a_forged_notification(self):
        forged = {
            "OrderTrackingId": "00000000-0000-0000-0000-000000000000",
            "OrderNotificationType": "IPNCHANGE",
            "OrderMerchantReference": "PAW-0-forged",
        }
        response = self.call("POST", "webhook/", json=forged)
        self.assertIn(response.status_code, (400, 404))

    def test_the_webhook_does_not_accept_get(self):
        self.assertEqual(self.call("GET", "webhook/").status_code, 405)

    # -- need PAYMENT_TEST_AUTH_HEADER (a customer's token) --------------------

    def test_a_logged_in_customer_sees_the_payment_methods(self):
        self.need_login_token()
        response = self.call("GET", "methods/", authenticated=True)

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["methods"])
        self.assertEqual(len(data["currency"]), 3)

    def test_an_unknown_order_has_no_payment_status(self):
        self.need_login_token()
        response = self.call("GET", "orders/999999999/", authenticated=True)
        self.assertEqual(response.status_code, 404)

    # -- extra checks that only make sense on the live server -------------------

    def test_live_server_uses_https(self):
        if not IS_LIVE:
            self.skipTest("Set PAYMENT_TEST_IS_LIVE=1 for live-only checks.")
        self.assertTrue(API_BASE.startswith("https://"), "The live API must use https.")

    def test_live_server_has_no_sandbox_simulation_endpoint(self):
        if not IS_LIVE:
            self.skipTest("Set PAYMENT_TEST_IS_LIVE=1 for live-only checks.")
        response = self.call(
            "POST", "sandbox/simulate/", json={"reference": "x", "result": "success"}
        )
        self.assertEqual(
            response.status_code,
            404,
            "The fake-payment endpoint is reachable on the live server.",
        )
