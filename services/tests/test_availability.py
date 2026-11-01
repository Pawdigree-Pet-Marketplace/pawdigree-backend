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

#--------------------------------remove a time slot--------------------------------
class RemoveSlotTests(AvailabilityTestCase):
    def setUp(self):
        super().setUp()
        self.slot = AvailabilitySlot.objects.create(
            service=self.service, weekday=0,
            start_time="09:00", end_time="12:00",
        )

    def detail_url(self, service=None, slot=None):
        service = service or self.service
        slot = slot or self.slot
        return reverse(
            "service-slot-detail",
            kwargs={"service_id": service.pk, "pk": slot.pk},
        )

    def test_vendor_can_remove_a_slot(self):
        response = self.client.delete(self.detail_url())

        self.assertEqual(response.status_code, 204)
        self.assertFalse(AvailabilitySlot.objects.filter(pk=self.slot.pk).exists())

    def test_removing_twice_returns_404(self):
        self.client.delete(self.detail_url())

        self.assertEqual(self.client.delete(self.detail_url()).status_code, 404)

    def test_another_vendor_cannot_remove_it(self):
        self.client.force_authenticate(self.other)

        self.assertEqual(self.client.delete(self.detail_url()).status_code, 404)
        self.assertTrue(AvailabilitySlot.objects.filter(pk=self.slot.pk).exists())

    def test_slot_with_the_wrong_service_in_the_url_returns_404(self):
        second = Service.objects.create(
            business=self.business, name="Walking",
            service_type="walking", description="Walks",
            price="10.00", duration=30,
        )

        response = self.client.delete(self.detail_url(service=second))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(AvailabilitySlot.objects.filter(pk=self.slot.pk).exists())

    def test_customer_cannot_remove_a_slot(self):
        self.client.force_authenticate(self.customer)

        self.assertEqual(self.client.delete(self.detail_url()).status_code, 403)

    def test_removed_slot_leaves_the_list(self):
        self.client.delete(self.detail_url())

        response = self.client.get(self.slots_url())

        self.assertEqual(rows(response), [])
        
        
class CalendarTests(AvailabilityTestCase):
    def calendar(self):
        url = reverse("service-availability", kwargs={"service_id": self.service.pk})
        return self.client.get(url)

    def test_calendar_has_all_seven_days_starting_on_monday(self):
        response = self.calendar()

        self.assertEqual(response.status_code, 200)
        days = response.json()["days"]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]["day"], "Monday")
        self.assertEqual(days[6]["day"], "Sunday")

    def test_empty_schedule_gives_seven_empty_days(self):
        days = self.calendar().json()["days"]

        self.assertEqual([day["slots"] for day in days], [[]] * 7)

    def test_slots_are_grouped_by_day_in_time_order(self):
        AvailabilitySlot.objects.create(
            service=self.service, weekday=0, start_time="13:00", end_time="15:00"
        )
        AvailabilitySlot.objects.create(
            service=self.service, weekday=0, start_time="09:00", end_time="12:00"
        )
        AvailabilitySlot.objects.create(
            service=self.service, weekday=2, start_time="09:00", end_time="12:00"
        )

        days = self.calendar().json()["days"]

        self.assertEqual(
            [slot["start_time"] for slot in days[0]["slots"]],
            ["09:00:00", "13:00:00"],
        )
        self.assertEqual(days[1]["slots"], [])
        self.assertEqual(len(days[2]["slots"]), 1)

    def test_calendar_reports_the_service_details(self):
        data = self.calendar().json()

        self.assertEqual(data["service_name"], "Grooming")
        self.assertEqual(data["duration"], 60)
        self.assertEqual(data["availability_status"], "available")

    def test_another_vendor_gets_404(self):
        self.client.force_authenticate(self.other)

        self.assertEqual(self.calendar().status_code, 404)

    def test_customer_gets_403(self):
        self.client.force_authenticate(self.customer)

        self.assertEqual(self.calendar().status_code, 403)