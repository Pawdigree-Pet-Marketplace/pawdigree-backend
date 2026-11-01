from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from services.models import AvailabilitySlot, Service


def rows(response):
    """The list of items, whether or not the response is paginated."""
    data = response.json()
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


class AvailabilityTestCase(TestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username="vendor1", email="vendor@example.com",
            password="Test12345!", role=User.Role.VENDOR,
        )
        self.other = User.objects.create_user(
            username="vendor2", email="vendor2@example.com",
            password="Test12345!", role=User.Role.VENDOR,
        )
        self.customer = User.objects.create_user(
            username="customer1", email="customer@example.com",
            password="Test12345!", role=User.Role.CUSTOMER,
        )
        self.business = Business.objects.create(
            vendor=self.vendor, name="Paws Place", description="Pets",
            contact="0700000000", email="shop@example.com",
            address="1 Main St", city_district="Kampala",
        )
        # A one-hour service, so slots shorter than 60 minutes are too short.
        self.service = Service.objects.create(
            business=self.business, name="Grooming",
            service_type="grooming", description="Full groom",
            price="25.00", duration=60,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.vendor)

    def slots_url(self, service=None):
        service = service or self.service
        return reverse("service-slot-list", kwargs={"service_id": service.pk})

    def add_slot(self, **body):
        data = {"weekday": 0, "start_time": "09:00", "end_time": "12:00"}
        data.update(body)
        return self.client.post(self.slots_url(), data, format="json")


class AddSlotTests(AvailabilityTestCase):
    def test_vendor_can_add_a_slot(self):
        response = self.add_slot()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["weekday"], 0)
        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_end_must_be_after_start(self):
        self.assertEqual(
            self.add_slot(start_time="12:00", end_time="09:00").status_code, 400
        )
        self.assertEqual(
            self.add_slot(start_time="09:00", end_time="09:00").status_code, 400
        )
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_slot_shorter_than_the_service_is_rejected(self):
        response = self.add_slot(start_time="09:00", end_time="09:30")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_slot_exactly_as_long_as_the_service_is_allowed(self):
        response = self.add_slot(start_time="09:00", end_time="10:00")

        self.assertEqual(response.status_code, 201)

    def test_weekday_must_be_between_0_and_6(self):
        self.assertEqual(self.add_slot(weekday=7).status_code, 400)
        self.assertEqual(self.add_slot(weekday=-1).status_code, 400)

    def test_overlapping_slots_are_rejected(self):
        self.add_slot(start_time="09:00", end_time="12:00")

        for start, end in (("11:00", "13:00"), ("10:00", "11:00"), ("09:00", "12:00")):
            with self.subTest(start=start, end=end):
                response = self.add_slot(start_time=start, end_time=end)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(AvailabilitySlot.objects.count(), 1)

    def test_back_to_back_slots_are_allowed(self):
        self.add_slot(start_time="09:00", end_time="12:00")

        response = self.add_slot(start_time="12:00", end_time="15:00")

        self.assertEqual(response.status_code, 201)

    def test_same_times_on_another_day_are_allowed(self):
        self.add_slot(weekday=0)

        self.assertEqual(self.add_slot(weekday=1).status_code, 201)

    def test_another_vendors_service_returns_404(self):
        self.client.force_authenticate(self.other)

        self.assertEqual(self.add_slot().status_code, 404)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_customer_cannot_add_a_slot(self):
        self.client.force_authenticate(self.customer)

        self.assertEqual(self.add_slot().status_code, 403)

    def test_anonymous_user_is_turned_away(self):
        response = APIClient().post(
            self.slots_url(),
            {"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
            format="json",
        )

        self.assertIn(response.status_code, (401, 403))

    def test_removed_service_returns_404(self):
        self.service.is_active = False
        self.service.save()

        self.assertEqual(self.add_slot().status_code, 404)

    def test_list_shows_only_this_services_slots_in_order(self):
        second = Service.objects.create(
            business=self.business, name="Walking",
            service_type="walking", description="Walks",
            price="10.00", duration=30,
        )
        AvailabilitySlot.objects.create(
            service=second, weekday=0, start_time="08:00", end_time="09:00"
        )
        self.add_slot(weekday=2, start_time="09:00", end_time="12:00")
        self.add_slot(weekday=0, start_time="13:00", end_time="15:00")

        response = self.client.get(self.slots_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["weekday"] for item in rows(response)], [0, 2])