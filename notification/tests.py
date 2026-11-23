from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

import reviews.tests as rt  # module import: its test classes are not collected here
from accounts.models import User
from adoptions.models import AdoptionApplication
from adoptions.services import (
    create_adoption_application,
    decide_adoption_application,
    reply_to_info_request,
    request_adoption_info,
)
from bookings.models import Booking
from bookings.services import (
    cancel_booking,
    change_booking_status,
    create_booking,
    reschedule_booking,
)
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from django.test import TestCase
from orders.models import VendorOrder
from orders.services import (
    change_status,
    checkout,
    expire_overdue_orders,
    mark_paid,
    mark_refunded,
)
from orders.models import Order
from orders.tests.test_pet_checkout import PAYLOAD, make_pet
from payments.models import Payment
from payments.services import process_gateway_event
from pets.notifications import notify_listing_approved
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Notification
from .services import create_notification
from reviews.services import create_reply, create_review
from businesses.models import Business

T = Notification.Type
STATUS = VendorOrder.Status


def notes(user, ntype=None):
    queryset = Notification.objects.filter(user=user)
    return queryset.filter(type=ntype) if ntype else queryset


class NotificationTestCase(TestCase):
    """Two customers, two vendors (one with two businesses), an admin."""

    def setUp(self):
        self.customer = make_user("notecust1", User.Role.CUSTOMER)
        self.other = make_user("notecust2", User.Role.CUSTOMER)
        self.vendor = make_user("notevendor1", User.Role.VENDOR)
        self.vendor2 = make_user("notevendor2", User.Role.VENDOR)
        self.admin = make_user("noteadmin", User.Role.ADMIN)
        self.business_a = make_business(self.vendor, name="Shop A")
        self.business_b = make_business(self.vendor, name="Shop B")
        self.business_c = make_business(self.vendor2, name="Shop C")
        self.category = make_category()

        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def login(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def run_hooks(self):
        """Run on_commit callbacks, as a real commit would."""
        return self.captureOnCommitCallbacks(execute=True)


# --------------------------------------------------------------------------
# create_notification
# --------------------------------------------------------------------------
class CreateNotificationTests(NotificationTestCase):
    def test_stores_business_and_reference(self):
        n = create_notification(
            self.vendor, T.NEW_ORDER, "hi",
            reference_id=7, reference_type="vendor_order", business=self.business_a,
        )
        self.assertEqual(n.business, self.business_a)
        self.assertEqual((n.reference_type, n.reference_id), ("vendor_order", "7"))
        self.assertEqual(n.user_role, User.Role.VENDOR)
        self.assertFalse(n.is_read)

    def test_uuid_references_are_supported(self):
        n = create_notification(
            self.vendor, T.BUSINESS_VERIFICATION, "x",
            reference_id=self.business_a.pk, reference_type="business",
        )
        self.assertEqual(n.reference_id, str(self.business_a.pk))

    def test_same_event_key_creates_one_notification(self):
        for _ in range(3):
            create_notification(self.customer, T.ORDER_PLACED, "x", event_key="e1")
        self.assertEqual(notes(self.customer).count(), 1)

    def test_same_event_key_for_different_users_creates_both(self):
        create_notification(self.customer, T.ORDER_PLACED, "x", event_key="e1")
        create_notification(self.other, T.ORDER_PLACED, "x", event_key="e1")
        self.assertEqual(Notification.objects.count(), 2)

    def test_without_a_key_every_call_creates_one(self):
        create_notification(self.customer, T.ORDER_PLACED, "x")
        create_notification(self.customer, T.ORDER_PLACED, "x")
        self.assertEqual(notes(self.customer).count(), 2)


# --------------------------------------------------------------------------
# Orders and payments
# --------------------------------------------------------------------------
class OrderNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(
            self.business_a, self.category, name="Toy", price="10.00", stock=20
        )
        self.pet = make_pet(self.vendor2, self.business_c, name="Rex")

    def checkout_mixed(self):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        CartItem.objects.create(cart=cart, pet=self.pet, quantity=1)
        with self.run_hooks():
            return checkout(self.customer, PAYLOAD)

    def test_checkout_notifies_only_the_customer(self):
        self.checkout_mixed()
        self.assertEqual(notes(self.customer, T.ORDER_PLACED).count(), 1)
        # Vendors only hear about an order once it is paid.
        self.assertEqual(notes(self.vendor).count(), 0)
        self.assertEqual(notes(self.vendor2).count(), 0)

    def test_payment_notifies_customer_and_each_vendor_once(self):
        order = self.checkout_mixed()
        with self.run_hooks():
            mark_paid(order.pk)

        self.assertEqual(notes(self.customer, T.PAYMENT_CONFIRMED).count(), 1)

        merch = notes(self.vendor, T.NEW_ORDER).get()
        self.assertEqual(merch.business, self.business_a)
        self.assertEqual(merch.reference_type, "vendor_order")
        self.assertIn("Toy x2", merch.message)

        sale = notes(self.vendor2, T.NEW_PET_SALE).get()
        self.assertEqual(sale.business, self.business_c)
        self.assertIn("Rex", sale.message)

        # Nobody gets the other vendor's notification.
        self.assertEqual(notes(self.vendor, T.NEW_PET_SALE).count(), 0)
        self.assertEqual(notes(self.vendor2, T.NEW_ORDER).count(), 0)

    def test_a_repeated_payment_does_not_notify_twice(self):
        order = self.checkout_mixed()
        with self.run_hooks():
            mark_paid(order.pk)
        with self.run_hooks():
            mark_paid(order.pk)
        self.assertEqual(Notification.objects.filter(type=T.PAYMENT_CONFIRMED).count(), 1)
        self.assertEqual(Notification.objects.filter(type=T.NEW_ORDER).count(), 1)

    def test_status_changes_notify_the_customer(self):
        order = self.checkout_mixed()
        mark_paid(order.pk)
        vendor_order = order.vendor_orders.get(business=self.business_a)

        for step in (STATUS.PROCESSING, STATUS.SHIPPED, STATUS.DELIVERED):
            with self.run_hooks():
                change_status(vendor_order.pk, step, self.vendor)

        messages = list(notes(self.customer, T.ORDER_STATUS).values_list("message", flat=True))
        self.assertEqual(len(messages), 3)
        self.assertTrue(any("delivered" in m and "review" in m for m in messages))

    def test_cancelling_a_paid_order_notifies_customer_and_admins(self):
        order = self.checkout_mixed()
        mark_paid(order.pk)
        vendor_order = order.vendor_orders.get(business=self.business_a)
        with self.run_hooks():
            change_status(vendor_order.pk, STATUS.CANCELLED, self.vendor)
        self.assertEqual(notes(self.customer, T.ORDER_CANCELLED).count(), 1)
        self.assertEqual(notes(self.admin, T.REFUND_REQUIRED).count(), 1)

    def test_confirming_a_refund_notifies_the_customer(self):
        order = self.checkout_mixed()
        mark_paid(order.pk)
        vendor_order = order.vendor_orders.get(business=self.business_a)
        change_status(vendor_order.pk, STATUS.CANCELLED, self.vendor)
        with self.run_hooks():
            mark_refunded(vendor_order.pk, self.admin)
        self.assertEqual(notes(self.customer, T.REFUND_CONFIRMED).count(), 1)

    def test_an_expired_order_notifies_the_customer(self):
        order = self.checkout_mixed()
        Order.objects.filter(pk=order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        with self.run_hooks():
            expire_overdue_orders()
        self.assertEqual(notes(self.customer, T.ORDER_EXPIRED).count(), 1)

    def test_a_refused_checkout_creates_nothing(self):
        with self.run_hooks():
            with self.assertRaises(ValidationError):
                checkout(self.customer, PAYLOAD)  # empty cart
        self.assertEqual(Notification.objects.count(), 0)

    def test_nothing_is_sent_if_the_transaction_never_commits(self):
        # Without running the on_commit callbacks, a rolled-back action sends nothing.
        order = self.checkout_mixed()
        mark_paid(order.pk)
        self.assertEqual(notes(self.vendor, T.NEW_ORDER).count(), 0)


class PaymentNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(
            self.business_a, self.category, name="Toy", price="10.00", stock=20
        )
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        self.order = checkout(self.customer, PAYLOAD)
        self.payment = Payment.objects.create(
            order=self.order, method="pesapal", amount=self.order.total_amount,
            currency=settings.PAYMENT_CURRENCY,
            gateway_reference=f"PAW-{self.order.pk}-test",
        )

    def event(self, succeeded=True, amount=None, currency=None, reason=""):
        return SimpleNamespace(
            reference=self.payment.gateway_reference, transaction_id="t-1", payload={},
            succeeded=succeeded, failure_reason=reason,
            amount=self.payment.amount if amount is None else amount,
            currency=currency or self.payment.currency,
        )

    def test_successful_payment_notifies_customer_and_vendor(self):
        with self.run_hooks():
            process_gateway_event(self.event())
        self.assertEqual(notes(self.customer, T.PAYMENT_CONFIRMED).count(), 1)
        self.assertEqual(notes(self.vendor, T.NEW_ORDER).count(), 1)

    def test_a_failed_payment_sends_no_success_notification(self):
        with self.run_hooks():
            process_gateway_event(self.event(succeeded=False, reason="Declined"))
        self.assertEqual(notes(self.customer, T.PAYMENT_FAILED).count(), 1)
        self.assertEqual(notes(self.customer, T.PAYMENT_CONFIRMED).count(), 0)
        self.assertEqual(notes(self.vendor).count(), 0)

    def test_a_wrong_amount_sends_no_success_notification(self):
        with self.run_hooks():
            process_gateway_event(self.event(amount=Decimal("1.00")))
        self.assertEqual(notes(self.customer, T.PAYMENT_CONFIRMED).count(), 0)
        self.assertEqual(notes(self.vendor).count(), 0)
        self.assertEqual(notes(self.customer, T.PAYMENT_FAILED).count(), 1)
        self.assertEqual(notes(self.admin, T.REFUND_REQUIRED).count(), 1)

    def test_a_late_payment_is_a_refund_not_a_sale(self):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        expire_overdue_orders()
        with self.run_hooks():
            process_gateway_event(self.event())
        self.assertEqual(notes(self.customer, T.PAYMENT_CONFIRMED).count(), 0)
        self.assertEqual(notes(self.vendor, T.NEW_ORDER).count(), 0)
        self.assertEqual(notes(self.admin, T.REFUND_REQUIRED).count(), 1)

    def test_a_webhook_retry_does_not_notify_twice(self):
        with self.run_hooks():
            process_gateway_event(self.event())
        with self.run_hooks():
            process_gateway_event(self.event())
        self.assertEqual(notes(self.customer, T.PAYMENT_CONFIRMED).count(), 1)


# --------------------------------------------------------------------------
# Bookings
# --------------------------------------------------------------------------
class BookingNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.service = rt.make_service(self.business_a)

    def free(self, start):
        return mock.patch("bookings.services.free_start_times", return_value=[start])

    def test_new_booking_notifies_the_vendor_with_the_business(self):
        start = timezone.now() + timedelta(days=2)
        with self.free(start), self.run_hooks():
            create_booking(self.customer, self.service, start)
        n = notes(self.vendor, T.BOOKING_NEW).get()
        self.assertEqual(n.business, self.business_a)
        self.assertEqual(n.reference_type, "booking")
        self.assertEqual(notes(self.customer).count(), 0)

    def test_accepting_and_declining_notify_the_customer(self):
        accepted = rt.make_booking(self.customer, self.service, Booking.Status.PENDING)
        declined = rt.make_booking(self.customer, self.service, Booking.Status.PENDING, days=2)
        with self.run_hooks():
            change_booking_status(self.vendor, accepted.pk, Booking.Status.ACCEPTED)
        with self.run_hooks():
            change_booking_status(
                self.vendor, declined.pk, Booking.Status.DECLINED, "Fully booked"
            )
        messages = list(notes(self.customer, T.BOOKING_UPDATED).values_list("message", flat=True))
        self.assertEqual(len(messages), 2)
        self.assertTrue(any("confirmed" in m for m in messages))
        self.assertTrue(any("Fully booked" in m for m in messages))

    def test_completing_notifies_the_customer(self):
        booking = rt.make_booking(self.customer, self.service, Booking.Status.ACCEPTED, days=-2)
        with self.run_hooks():
            change_booking_status(self.vendor, booking.pk, Booking.Status.COMPLETED)
        self.assertIn("review", notes(self.customer, T.BOOKING_UPDATED).get().message)

    def test_a_refused_change_notifies_nobody(self):
        booking = rt.make_booking(self.customer, self.service, Booking.Status.PENDING)
        with self.run_hooks():
            with self.assertRaises(ValidationError):
                change_booking_status(self.vendor, booking.pk, Booking.Status.COMPLETED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_customer_cancelling_notifies_the_vendor(self):
        booking = rt.make_booking(self.customer, self.service, Booking.Status.ACCEPTED)
        with self.run_hooks():
            cancel_booking(self.customer, booking.pk)
        n = notes(self.vendor, T.BOOKING_CANCELLED).get()
        self.assertEqual(n.business, self.business_a)

    def test_rescheduling_notifies_the_vendor(self):
        booking = rt.make_booking(self.customer, self.service, Booking.Status.ACCEPTED)
        new_start = timezone.now() + timedelta(days=5)
        with self.free(new_start), self.run_hooks():
            reschedule_booking(self.customer, booking.pk, new_start)
        self.assertEqual(notes(self.vendor, T.BOOKING_RESCHEDULED).count(), 1)


class BookingReminderTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.service = rt.make_service(self.business_a)

    def booking(self, hours, status=Booking.Status.ACCEPTED):
        start = timezone.now() + timedelta(hours=hours)
        return Booking.objects.create(
            customer=self.customer, service=self.service, start_at=start,
            end_at=start + timedelta(minutes=60), status=status,
        )

    def test_reminds_an_accepted_booking_within_24_hours(self):
        self.booking(10)
        call_command("send_booking_reminders")
        n = notes(self.customer, T.BOOKING_REMINDER).get()
        self.assertEqual(n.reference_type, "booking")

    def test_running_twice_sends_one_reminder(self):
        self.booking(10)
        call_command("send_booking_reminders")
        call_command("send_booking_reminders")
        self.assertEqual(notes(self.customer, T.BOOKING_REMINDER).count(), 1)

    def test_skips_far_away_unaccepted_cancelled_and_past_bookings(self):
        self.booking(72)
        self.booking(10, Booking.Status.PENDING)
        self.booking(11, Booking.Status.CANCELLED)
        self.booking(-5)
        call_command("send_booking_reminders")
        self.assertEqual(notes(self.customer, T.BOOKING_REMINDER).count(), 0)

    def test_vendor_gets_no_reminder(self):
        self.booking(10)
        call_command("send_booking_reminders")
        self.assertEqual(notes(self.vendor).count(), 0)


# --------------------------------------------------------------------------
# Adoptions
# --------------------------------------------------------------------------
class AdoptionNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.pet = make_pet(self.vendor, self.business_a, name="Milo", listing_type="ADOPTION")
        self.data = {
            "home_type": AdoptionApplication.HomeType.HOUSE,
            "previous_pet_experience": AdoptionApplication.Experience.SOME,
            "message": "I would love to adopt.",
        }

    def apply(self):
        with self.run_hooks():
            return create_adoption_application(self.customer, self.pet.pk, dict(self.data))

    def test_submission_notifies_vendor_and_customer(self):
        application = self.apply()
        vendor_note = notes(self.vendor, T.ADOPTION_NEW).get()
        self.assertEqual(vendor_note.business, self.business_a)
        self.assertEqual(vendor_note.reference_type, "adoption")
        self.assertEqual(vendor_note.reference_id, str(application.pk))
        self.assertEqual(notes(self.customer, T.ADOPTION_UPDATE).count(), 1)

    def test_info_request_and_reply(self):
        application = self.apply()
        with self.run_hooks():
            request_adoption_info(application.pk, self.vendor, "Do you have a garden?")
        self.assertEqual(notes(self.customer, T.ADOPTION_UPDATE).count(), 2)
        with self.run_hooks():
            reply_to_info_request(application.pk, self.customer, "Yes")
        self.assertEqual(notes(self.vendor, T.ADOPTION_REPLY).count(), 1)

    def test_approval_and_rejection_notify_the_customer(self):
        application = self.apply()
        with self.run_hooks():
            decide_adoption_application(
                application.pk, self.vendor, AdoptionApplication.Status.APPROVED
            )
        self.assertTrue(
            any("approved" in n.message for n in notes(self.customer, T.ADOPTION_UPDATE))
        )

        second = make_pet(self.vendor, self.business_a, name="Kit", listing_type="ADOPTION")
        with self.run_hooks():
            other_app = create_adoption_application(self.other, second.pk, dict(self.data))
        with self.run_hooks():
            decide_adoption_application(
                other_app.pk, self.vendor, AdoptionApplication.Status.REJECTED, "Not suitable"
            )
        self.assertTrue(
            any("Not suitable" in n.message for n in notes(self.other, T.ADOPTION_UPDATE))
        )

    def test_vendor_decisions_do_not_notify_the_vendor(self):
        application = self.apply()
        before = notes(self.vendor).count()
        with self.run_hooks():
            decide_adoption_application(
                application.pk, self.vendor, AdoptionApplication.Status.APPROVED
            )
        self.assertEqual(notes(self.vendor).count(), before)

    def test_admin_decisions_also_notify_the_vendor(self):
        application = self.apply()
        with self.run_hooks():
            decide_adoption_application(
                application.pk, self.admin, AdoptionApplication.Status.APPROVED
            )
        self.assertEqual(notes(self.vendor, T.ADOPTION_UPDATE).count(), 1)

    def test_a_refused_decision_notifies_nobody(self):
        application = self.apply()
        decide_adoption_application(
            application.pk, self.vendor, AdoptionApplication.Status.REJECTED
        )
        before = Notification.objects.count()
        with self.run_hooks():
            with self.assertRaises(ValidationError):
                decide_adoption_application(
                    application.pk, self.vendor, AdoptionApplication.Status.APPROVED
                )
        self.assertEqual(Notification.objects.count(), before)


# --------------------------------------------------------------------------
# Listings (existing notifications now carry business and reference type)
# --------------------------------------------------------------------------
class ListingNotificationTests(NotificationTestCase):
    def test_listing_notification_carries_business_and_type(self):
        pet = make_pet(self.vendor, self.business_b, name="Rex")
        notify_listing_approved(pet)
        n = notes(self.vendor, T.LISTING_APPROVED).get()
        self.assertEqual(n.business, self.business_b)
        self.assertEqual((n.reference_type, n.reference_id), ("pet", str(pet.pk)))


# --------------------------------------------------------------------------
# Reviews and replies
# --------------------------------------------------------------------------
class ReviewNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(
            self.business_a, self.category, name="Toy", price="10.00", stock=20
        )
        rt.buy(self.customer, self.vendor, product=self.product)
        with self.run_hooks():
            self.review = create_review(
                customer=self.customer, kind="product",
                target_id=self.product.pk, rating=4, comment="Good",
            )

    def reply(self, user, body="Thanks!"):
        with self.run_hooks():
            return create_reply(author=user, review_id=self.review.pk, body=body)

    def test_new_review_notifies_the_vendor_with_the_business(self):
        n = notes(self.vendor, T.NEW_REVIEW).get()
        self.assertEqual(n.business, self.business_a)
        self.assertEqual((n.reference_type, n.reference_id), ("product", str(self.product.pk)))
        self.assertEqual(notes(self.customer, T.NEW_REVIEW).count(), 0)

    def test_vendor_reply_notifies_the_review_author_only(self):
        self.reply(self.vendor)
        self.assertEqual(notes(self.customer, T.REVIEW_REPLY).count(), 1)
        self.assertEqual(notes(self.vendor, T.REVIEW_REPLY).count(), 0)

    def test_customer_reply_notifies_author_and_vendor(self):
        self.reply(self.other)
        self.assertEqual(notes(self.customer, T.REVIEW_REPLY).count(), 1)
        self.assertEqual(notes(self.vendor, T.REVIEW_REPLY).get().business, self.business_a)
        self.assertEqual(notes(self.other, T.REVIEW_REPLY).count(), 0)

    def test_author_replying_notifies_only_the_vendor(self):
        self.reply(self.customer)
        self.assertEqual(notes(self.customer, T.REVIEW_REPLY).count(), 0)
        self.assertEqual(notes(self.vendor, T.REVIEW_REPLY).count(), 1)

    def test_admin_reply_notifies_author_and_vendor(self):
        self.reply(self.admin)
        self.assertEqual(notes(self.customer, T.REVIEW_REPLY).count(), 1)
        self.assertEqual(notes(self.vendor, T.REVIEW_REPLY).count(), 1)

    def test_several_replies_are_allowed(self):
        for user in (self.vendor, self.other, self.admin, self.vendor):
            self.reply(user)
        self.assertEqual(self.review.replies.count(), 4)

    def test_another_vendor_cannot_reply(self):
        with self.assertRaises(PermissionDenied):
            create_reply(author=self.vendor2, review_id=self.review.pk, body="Spam")
        self.assertEqual(self.review.replies.count(), 0)

    def test_empty_reply_is_refused(self):
        with self.assertRaises(ValidationError):
            create_reply(author=self.other, review_id=self.review.pk, body="   ")

    def test_replies_over_the_api(self):
        url = reverse("review-replies", kwargs={"pk": self.review.pk})
        self.assertEqual(self.login(self.other).post(url, {"body": "Same here"}).status_code, 201)
        self.assertEqual(APIClient().post(url, {"body": "x"}).status_code, 401)
        self.assertEqual(
            self.login(self.vendor2).post(url, {"body": "x"}).status_code, 403
        )
        public = APIClient().get(url)
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data["count"], 1)
        self.assertEqual(public.data["results"][0]["author_role"], User.Role.CUSTOMER)

    def test_only_author_or_admin_can_delete_a_reply(self):
        reply = create_reply(author=self.other, review_id=self.review.pk, body="Hi")
        url = reverse("review-reply-detail", kwargs={"pk": reply.pk})
        self.assertEqual(self.login(self.customer).delete(url).status_code, 404)
        self.assertEqual(self.login(self.other).delete(url).status_code, 204)

        again = create_reply(author=self.other, review_id=self.review.pk, body="Hi")
        url = reverse("review-reply-detail", kwargs={"pk": again.pk})
        self.assertEqual(self.login(self.admin).delete(url).status_code, 204)


# --------------------------------------------------------------------------
# API: ownership, business filtering, unread counts, read status
# --------------------------------------------------------------------------
class NotificationAPITests(NotificationTestCase):
    list_url = property(lambda self: reverse("notification-list"))
    count_url = property(lambda self: reverse("notification-unread-count"))
    all_read_url = property(lambda self: reverse("notification-mark-all-read"))

    def setUp(self):
        super().setUp()
        self.a1 = create_notification(
            self.vendor, T.NEW_ORDER, "A1", business=self.business_a, reference_type="vendor_order", reference_id=1
        )
        self.a2 = create_notification(self.vendor, T.NEW_REVIEW, "A2", business=self.business_a)
        self.b1 = create_notification(self.vendor, T.NEW_ORDER, "B1", business=self.business_b)
        self.legacy = create_notification(self.vendor, T.LISTING_APPROVED, "Old")
        self.c1 = create_notification(self.vendor2, T.NEW_ORDER, "C1", business=self.business_c)
        self.cust1 = create_notification(self.customer, T.ORDER_PLACED, "Mine")
        self.cust2 = create_notification(self.other, T.ORDER_PLACED, "Theirs")

    def messages(self, response):
        return {n["message"] for n in response.data["results"]}

    # ownership
    def test_requires_login(self):
        self.assertEqual(APIClient().get(self.list_url).status_code, 401)
        self.assertEqual(APIClient().get(self.count_url).status_code, 401)
        self.assertEqual(APIClient().post(self.all_read_url).status_code, 401)

    def test_customer_sees_only_their_own(self):
        self.assertEqual(self.messages(self.client.get(self.list_url)), {"Mine"})

    def test_vendors_and_customers_cannot_see_each_others(self):
        vendor_view = self.messages(self.login(self.vendor).get(self.list_url))
        self.assertNotIn("Mine", vendor_view)
        self.assertNotIn("C1", vendor_view)
        self.assertNotIn("A1", self.messages(self.client.get(self.list_url)))

    def test_cannot_mark_someone_elses_notification_read(self):
        url = reverse("notification-mark-read", kwargs={"pk": self.a1.pk})
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.login(self.vendor2).post(url).status_code, 404)
        self.a1.refresh_from_db()
        self.assertFalse(self.a1.is_read)

    # business filtering
    def test_main_dashboard_returns_every_business_and_legacy_rows(self):
        data = self.login(self.vendor).get(self.list_url)
        self.assertEqual(self.messages(data), {"A1", "A2", "B1", "Old"})

    def test_business_view_returns_only_that_business(self):
        vendor = self.login(self.vendor)
        a = vendor.get(self.list_url, {"business": str(self.business_a.pk)})
        b = vendor.get(self.list_url, {"business": str(self.business_b.pk)})
        self.assertEqual(self.messages(a), {"A1", "A2"})
        self.assertEqual(self.messages(b), {"B1"})

    def test_another_vendors_business_is_404(self):
        response = self.login(self.vendor).get(
            self.list_url, {"business": str(self.business_c.pk)}
        )
        self.assertEqual(response.status_code, 404)

    def test_bad_business_filters(self):
        self.assertEqual(
            self.login(self.vendor).get(self.list_url, {"business": "nope"}).status_code, 400
        )
        self.assertEqual(
            self.client.get(self.list_url, {"business": str(self.business_a.pk)}).status_code, 400
        )

    def test_notifications_expose_business_and_reference_fields(self):
        data = self.login(self.vendor).get(
            self.list_url, {"business": str(self.business_a.pk)}
        ).data["results"]
        first = next(n for n in data if n["message"] == "A1")
        self.assertEqual(first["business_id"], self.business_a.pk)
        self.assertEqual(first["business_name"], "Shop A")
        self.assertEqual((first["reference_type"], first["reference_id"]), ("vendor_order", "1"))

    def test_other_list_filters(self):
        vendor = self.login(self.vendor)
        only_reviews = vendor.get(self.list_url, {"type": "NEW_REVIEW"})
        self.assertEqual(self.messages(only_reviews), {"A2"})
        self.assertEqual(vendor.get(self.list_url, {"type": "BOGUS"}).status_code, 400)
        self.assertEqual(vendor.get(self.list_url, {"is_read": "maybe"}).status_code, 400)

    # unread counts
    def test_unread_count_total_scoped_and_per_business(self):
        vendor = self.login(self.vendor)
        total = vendor.get(self.count_url).data
        self.assertEqual(total["unread"], 4)
        self.assertEqual(
            total["by_business"],
            {str(self.business_a.pk): 2, str(self.business_b.pk): 1, "unassigned": 1},
        )
        scoped = vendor.get(self.count_url, {"business": str(self.business_a.pk)}).data
        self.assertEqual(scoped["unread"], 2)

    def test_customer_count_is_theirs_and_has_no_breakdown(self):
        data = self.client.get(self.count_url).data
        self.assertEqual(data, {"unread": 1})

    def test_count_drops_when_read(self):
        self.client.post(reverse("notification-mark-read", kwargs={"pk": self.cust1.pk}))
        self.assertEqual(self.client.get(self.count_url).data["unread"], 0)

    # read status
    def test_mark_read_sets_the_flag_and_keeps_timestamps_sane(self):
        url = reverse("notification-mark-read", kwargs={"pk": self.cust1.pk})
        created = self.cust1.created_at
        self.assertEqual(self.client.post(url).status_code, 200)
        self.cust1.refresh_from_db()
        self.assertTrue(self.cust1.is_read)
        self.assertEqual(self.cust1.created_at, created)
        stamp = self.cust1.updated_at
        self.client.post(url)  # reading again changes nothing
        self.cust1.refresh_from_db()
        self.assertEqual(self.cust1.updated_at, stamp)

    def test_mark_all_read_only_touches_my_notifications(self):
        self.client.post(self.all_read_url)
        self.cust1.refresh_from_db()
        self.cust2.refresh_from_db()
        self.assertTrue(self.cust1.is_read)
        self.assertFalse(self.cust2.is_read)

    def test_mark_all_read_for_one_business_leaves_the_rest_unread(self):
        vendor = self.login(self.vendor)
        response = vendor.post(
            self.all_read_url + f"?business={self.business_a.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread"], 0)
        self.a1.refresh_from_db()
        self.b1.refresh_from_db()
        self.legacy.refresh_from_db()
        self.assertTrue(self.a1.is_read)
        self.assertFalse(self.b1.is_read)
        self.assertFalse(self.legacy.is_read)
        # the switcher's badges still show what is left
        self.assertEqual(response.data["by_business"][str(self.business_b.pk)], 1)

    def test_is_read_filter(self):
        self.client.post(reverse("notification-mark-read", kwargs={"pk": self.cust1.pk}))
        create_notification(self.customer, T.ORDER_PLACED, "Second")
        unread = self.client.get(self.list_url, {"is_read": "false"})
        read = self.client.get(self.list_url, {"is_read": "true"})
        self.assertEqual(self.messages(unread), {"Second"})
        self.assertEqual(self.messages(read), {"Mine"})
        
        
        
class BusinessDecisionNotificationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", "adm@example.com", "Pass12345!", role="ADMIN")
        self.vendor = User.objects.create_user("ven", "ven@example.com", "Pass12345!", role="VENDOR")
        self.other_vendor = User.objects.create_user("ven2", "ven2@example.com", "Pass12345!", role="VENDOR")
        self.business = Business.objects.create(
            vendor=self.vendor, name="Paws", description="d", contact="0700000000",
            email="b@example.com", address="a", city_district="c",
            verification_status=Business.VerificationStatus.PENDING,
        )
        self.client.force_authenticate(self.admin)

    def decide(self, action, reason=""):
        url = reverse("business-admin-decision", args=[self.business.pk])
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, {"action": action, "reason": reason}, format="json")

    def set_status(self, status):
        Business.objects.filter(pk=self.business.pk).update(verification_status=status)

    def test_approval_notifies_the_vendor_with_a_business_link(self):
        self.assertEqual(self.decide("approve").status_code, 200)
        note = Notification.objects.get(user=self.vendor)
        self.assertEqual(note.type, Notification.Type.BUSINESS_VERIFICATION)
        self.assertEqual(note.business, self.business)
        self.assertEqual(note.reference_type, "business")
        self.assertEqual(note.reference_id, str(self.business.pk))
        self.assertIn("was approved", note.message)
        self.assertFalse(note.is_read)

    def test_request_changes_suspend_and_reapprove_each_notify(self):
        self.decide("request_changes", "Upload a clearer licence")
        self.set_status("approved")
        self.decide("suspend", "Complaints received")
        self.decide("reapprove")
        messages = list(
            Notification.objects.filter(user=self.vendor)
            .order_by("created_at").values_list("message", flat=True)
        )
        self.assertEqual(len(messages), 3)
        self.assertIn("needs changes", messages[0])
        self.assertIn("was suspended", messages[1])
        self.assertIn("was reinstated", messages[2])

    def test_other_users_get_nothing(self):
        self.decide("approve")
        self.assertEqual(Notification.objects.filter(user=self.other_vendor).count(), 0)
        self.assertEqual(Notification.objects.filter(user=self.admin).count(), 0)

    def test_a_rejected_decision_request_creates_no_notification(self):
        # Suspending a pending business is not allowed, so nothing may be sent.
        self.assertEqual(self.decide("suspend", "x").status_code, 400)
        self.assertEqual(Notification.objects.count(), 0)
        # Request-changes needs a reason.
        self.assertEqual(self.decide("request_changes").status_code, 400)
        self.assertEqual(Notification.objects.count(), 0)
        
    def test_rejection_notifies_the_vendor_and_is_recorded(self):
        response = self.decide("reject", "Documents do not match the business name")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verification_status"], "rejected")
        self.assertEqual(response.data["decision"]["action"], "reject")

        self.business.refresh_from_db()
        self.assertEqual(self.business.verification_status, "rejected")
        self.assertEqual(
            self.business.decision_reason, "Documents do not match the business name"
        )
        note = Notification.objects.get(user=self.vendor)
        self.assertEqual(note.type, Notification.Type.BUSINESS_VERIFICATION)
        self.assertEqual(note.business, self.business)
        self.assertIn("was not approved", note.message)
        self.assertNotIn("Documents do not match", note.message)  # reason stays off the card

        history = self.client.get(
            reverse("business-admin-decisions", args=[self.business.pk])
        )
        self.assertEqual(history.data[0]["action"], "reject")

    def test_rejection_requires_a_reason(self):
        self.assertEqual(self.decide("reject").status_code, 400)
        self.assertEqual(self.decide("reject", "   ").status_code, 400)
        self.business.refresh_from_db()
        self.assertEqual(self.business.verification_status, "pending")
        self.assertEqual(Notification.objects.count(), 0)

    def test_rejection_is_only_allowed_from_pending_or_changes_requested(self):
        self.set_status("changes_requested")
        self.assertEqual(self.decide("reject", "No reply from vendor").status_code, 200)

        for blocked in ("approved", "suspended", "rejected", "draft"):
            with self.subTest(status=blocked):
                self.set_status(blocked)
                Notification.objects.all().delete()
                self.assertEqual(self.decide("reject", "x").status_code, 400)
                self.assertEqual(Notification.objects.count(), 0)

    def test_a_rejected_vendor_can_reapply_and_be_approved(self):
        self.decide("reject", "Missing tax records")
        self.client.force_authenticate(self.vendor)
        reapply = self.client.post(
            reverse("business-reapply", args=[self.business.pk]),
            {"vendor_response": "Tax records uploaded"}, format="json",
        )
        self.assertEqual(reapply.status_code, 200)
        self.assertEqual(reapply.data["verification_status"], "pending")

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.decide("approve").status_code, 200)
        messages = list(
            Notification.objects.filter(user=self.vendor)
            .order_by("created_at").values_list("message", flat=True)
        )
        self.assertEqual(len(messages), 2)
        self.assertIn("was not approved", messages[0])
        self.assertIn("was approved", messages[1])

    def test_rejection_does_not_make_the_vendor_approved(self):
        self.decide("reject", "Not eligible")
        self.vendor.refresh_from_db()
        self.assertFalse(self.vendor.approved)   
