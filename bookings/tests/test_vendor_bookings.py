from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from bookings.models import Booking
from bookings.tests.helpers import make_service
from cart.tests.helpers import make_business, make_user


class VendorBookingListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vendor = make_user("booking_vendor", User.Role.VENDOR)
        self.other_vendor = make_user("other_booking_vendor", User.Role.VENDOR)
        self.customer = make_user("booking_customer", User.Role.CUSTOMER)
        self.customer.first_name = "Jamie"
        self.customer.last_name = "Customer"
        self.customer.phone = "+256700123456"
        self.customer.save()
        self.business = make_business(self.vendor, name="Vendor One")
        self.other_business = make_business(self.other_vendor, name="Vendor Two")
        self.service = make_service(self.business, name="Dog Grooming")
        self.other_service = make_service(
            self.other_business, name="Cat Sitting"
        )
        self.url = reverse("booking-vendor-list")

    def make_booking(
        self, service=None, customer=None, status_value=Booking.Status.PENDING
    ):
        start_at = timezone.now() + timedelta(days=5)
        return Booking.objects.create(
            customer=customer or self.customer,
            service=service or self.service,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=status_value,
            notes="Please call when you arrive.",
            decision_reason="Confirmed by vendor.",
        )

    def test_vendor_sees_their_own_bookings(self):
        statuses = [status_value for status_value, _ in Booking.Status.choices]
        for status_value in statuses:
            self.make_booking(status_value=status_value)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)
        self.assertEqual({row["status"] for row in response.data}, set(statuses))

    def test_vendor_does_not_see_another_vendors_bookings(self):
        self.make_booking(service=self.other_service)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_customer_cannot_access_vendor_bookings(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_access_vendor_bookings(self):
        response = self.client.get(self.url)

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_response_contains_vendor_facing_booking_fields(self):
        booking = self.make_booking()
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data[0]
        self.assertEqual(
            set(row),
            {
                "booking_id",
                "customer_id",
                "customer_name",
                "service_name",
                "start_at",
                "end_at",
                "status",
                "notes",
                "decision_reason",
                "created_at",
            },
        )
        self.assertEqual(row["booking_id"], booking.booking_id)
        self.assertEqual(row["customer_id"], self.customer.pk)
        self.assertEqual(row["customer_name"], "Jamie Customer")
        self.assertEqual(row["service_name"], "Dog Grooming")
        self.assertEqual(row["notes"], "Please call when you arrive.")
        self.assertEqual(row["decision_reason"], "Confirmed by vendor.")
        self.assertNotIn("email", row)
        self.assertNotIn("phone", row)

    def test_bookings_are_newest_first_and_id_descending_for_equal_timestamps(self):
        older = self.make_booking()
        newer_first = self.make_booking()
        newer_second = self.make_booking()
        now = timezone.now()
        Booking.objects.filter(pk=older.pk).update(created_at=now - timedelta(days=1))
        Booking.objects.filter(pk__in=(newer_first.pk, newer_second.pk)).update(
            created_at=now
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["booking_id"] for row in response.data],
            [newer_second.booking_id, newer_first.booking_id, older.booking_id],
        )
