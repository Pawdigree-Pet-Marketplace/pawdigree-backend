from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from pets.models import Pet

from ..models import AdoptionApplication, AdoptionInfoMessage
from ..serializers import AdoptionApplicationSerializer

Status = AdoptionApplication.Status


def make_user(name, role):
    return User.objects.create_user(
        username=name, email=f"{name}@example.com",
        password="Test12345!", role=role,
    )


class InfoRequestTestCase(TestCase):
    """Shared setup: people, a pet and one pending application."""

    def setUp(self):
        self.vendor = make_user("vendor1", User.Role.VENDOR)
        self.other_vendor = make_user("vendor2", User.Role.VENDOR)
        self.customer = make_user("customer1", User.Role.CUSTOMER)
        self.other_customer = make_user("customer2", User.Role.CUSTOMER)
        self.admin = make_user("admin1", User.Role.ADMIN)

        self.business = Business.objects.create(
            vendor=self.vendor, name="Paws Place", description="Pets",
            contact="0700000000", email="shop@example.com",
            address="1 Main St", city_district="Kampala",
        )
        self.pet = Pet.objects.create(
            vendor=self.vendor, business=self.business, name="Rex",
            age=6, gender="MALE", size="SMALL",
        )
        self.application = AdoptionApplication.objects.create(
            pet=self.pet, customer=self.customer, home_type="HOUSE",
            previous_pet_experience="SOME",
            message="I would love to adopt Rex.",
        )
        self.client = APIClient()

    def set_status(self, value):
        self.application.status = value
        self.application.save()

    def current_status(self):
        self.application.refresh_from_db()
        return self.application.status

    def post(self, route, body=None, application=None):
        application = application or self.application
        url = reverse(route, kwargs={"application_id": application.pk})
        return self.client.post(url, body or {}, format="json")

    def add_message(self, kind, body, author):
        return AdoptionInfoMessage.objects.create(
            application=self.application, author=author, kind=kind, body=body,
        )


class SerializerTests(InfoRequestTestCase):
    def test_application_shows_the_exchange_in_order(self):
        self.add_message("REQUEST", "Do you have a garden?", self.vendor)
        self.add_message("REPLY", "Yes, a fenced one.", self.customer)

        data = AdoptionApplicationSerializer(self.application).data

        kinds = [item["kind"] for item in data["info_messages"]]
        self.assertEqual(kinds, ["REQUEST", "REPLY"])

    def test_messages_do_not_expose_the_author(self):
        self.add_message("REQUEST", "Do you have a garden?", self.vendor)

        data = AdoptionApplicationSerializer(self.application).data

        self.assertEqual(
            set(data["info_messages"][0]),
            {"id", "kind", "body", "created_at"},
        )

    def test_application_without_messages_shows_an_empty_list(self):
        data = AdoptionApplicationSerializer(self.application).data

        self.assertEqual(data["info_messages"], [])