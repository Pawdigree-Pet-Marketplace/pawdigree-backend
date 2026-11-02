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
        
        
#-----------------------------vendor reuqests for information-------------------------

class RequestInfoTests(InfoRequestTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.vendor)

    def request_info(self, message="Do you have a garden?", **kwargs):
        return self.post("adoption-request-info", {"message": message}, **kwargs)

    def test_vendor_can_request_information(self):
        response = self.request_info()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.current_status(), "INFO_REQUESTED")

        row = AdoptionInfoMessage.objects.get()
        self.assertEqual(row.kind, "REQUEST")
        self.assertEqual(row.body, "Do you have a garden?")
        self.assertEqual(row.author, self.vendor)
        self.assertEqual(len(response.json()["info_messages"]), 1)

    def test_message_is_trimmed(self):
        self.request_info(message="   Any references?   ")

        self.assertEqual(AdoptionInfoMessage.objects.get().body, "Any references?")

    def test_blank_or_missing_message_is_rejected(self):
        for body in ({"message": ""}, {"message": "   "}, {}):
            with self.subTest(body=body):
                response = self.post("adoption-request-info", body)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.current_status(), "PENDING")
                self.assertEqual(AdoptionInfoMessage.objects.count(), 0)

    def test_message_over_2000_characters_is_rejected(self):
        response = self.request_info(message="x" * 2001)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AdoptionInfoMessage.objects.count(), 0)

    def test_only_a_pending_application_can_be_asked(self):
        for value in (
            Status.INFO_REQUESTED, Status.APPROVED,
            Status.REJECTED, Status.CANCELLED,
        ):
            with self.subTest(status=value):
                self.set_status(value)

                response = self.request_info()

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.current_status(), value)
                self.assertEqual(AdoptionInfoMessage.objects.count(), 0)

    def test_pet_that_is_gone_cannot_be_asked_about(self):
        self.pet.adoption_status = "ADOPTED"
        self.pet.save()
        self.assertEqual(self.request_info().status_code, 400)

        self.pet.adoption_status = "AVAILABLE"
        self.pet.is_active = False
        self.pet.save()
        self.assertEqual(self.request_info().status_code, 400)

        self.assertEqual(self.current_status(), "PENDING")

    def test_another_vendor_gets_404(self):
        self.client.force_authenticate(self.other_vendor)

        response = self.request_info()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.current_status(), "PENDING")
        self.assertEqual(AdoptionInfoMessage.objects.count(), 0)

    def test_pet_whose_business_belongs_to_someone_else_gets_404(self):
        other_business = Business.objects.create(
            vendor=self.other_vendor, name="Other Shop", description="Pets",
            contact="0700000001", email="other@example.com",
            address="2 Main St", city_district="Kampala",
        )
        self.pet.business = other_business
        self.pet.save()

        self.assertEqual(self.request_info().status_code, 404)

    def test_other_roles_are_turned_away(self):
        for user in (self.customer, self.other_customer, self.admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)

                self.assertEqual(self.request_info().status_code, 403)

        self.assertEqual(AdoptionInfoMessage.objects.count(), 0)

    def test_anonymous_user_is_turned_away(self):
        self.client.force_authenticate(None)

        self.assertIn(self.request_info().status_code, (401, 403))

    def test_unknown_application_returns_404(self):
        import uuid

        url = reverse(
            "adoption-request-info", kwargs={"application_id": uuid.uuid4()}
        )
        response = self.client.post(url, {"message": "Hi"}, format="json")

        self.assertEqual(response.status_code, 404)
        
        
#-----------------------------customer replies to vendor's request-------------------------
class ReplyTests(InfoRequestTestCase):
    def setUp(self):
        super().setUp()
        # Start with a question waiting for an answer.
        self.set_status(Status.INFO_REQUESTED)
        self.add_message("REQUEST", "Do you have a garden?", self.vendor)
        self.client.force_authenticate(self.customer)

    def reply(self, message="Yes, a fenced one.", **kwargs):
        return self.post("adoption-reply", {"message": message}, **kwargs)

    def test_customer_can_reply(self):
        response = self.reply()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.current_status(), "PENDING")

        row = AdoptionInfoMessage.objects.get(kind="REPLY")
        self.assertEqual(row.body, "Yes, a fenced one.")
        self.assertEqual(row.author, self.customer)

        kinds = [item["kind"] for item in response.json()["info_messages"]]
        self.assertEqual(kinds, ["REQUEST", "REPLY"])

    def test_blank_or_missing_reply_is_rejected(self):
        for body in ({"message": ""}, {"message": "   "}, {}):
            with self.subTest(body=body):
                response = self.post("adoption-reply", body)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.current_status(), "INFO_REQUESTED")

        self.assertEqual(AdoptionInfoMessage.objects.filter(kind="REPLY").count(), 0)

    def test_reply_over_2000_characters_is_rejected(self):
        self.assertEqual(self.reply(message="x" * 2001).status_code, 400)

    def test_can_only_reply_while_information_is_requested(self):
        for value in (
            Status.PENDING, Status.APPROVED, Status.REJECTED, Status.CANCELLED,
        ):
            with self.subTest(status=value):
                self.set_status(value)

                response = self.reply()

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.current_status(), value)

        self.assertEqual(AdoptionInfoMessage.objects.filter(kind="REPLY").count(), 0)

    def test_replying_twice_is_rejected(self):
        self.assertEqual(self.reply().status_code, 201)

        self.assertEqual(self.reply().status_code, 400)
        self.assertEqual(AdoptionInfoMessage.objects.filter(kind="REPLY").count(), 1)

    def test_reply_after_the_vendor_decided_is_refused(self):
        # The vendor approves while the question is still open.
        self.set_status(Status.APPROVED)

        response = self.reply()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.current_status(), "APPROVED")

    def test_another_customer_gets_404(self):
        self.client.force_authenticate(self.other_customer)

        response = self.reply()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.current_status(), "INFO_REQUESTED")
        self.assertEqual(AdoptionInfoMessage.objects.filter(kind="REPLY").count(), 0)

    def test_other_roles_are_turned_away(self):
        for user in (self.vendor, self.other_vendor, self.admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)

                self.assertEqual(self.reply().status_code, 403)

    def test_anonymous_user_is_turned_away(self):
        self.client.force_authenticate(None)

        self.assertIn(self.reply().status_code, (401, 403))

    def test_unknown_application_returns_404(self):
        import uuid

        url = reverse("adoption-reply", kwargs={"application_id": uuid.uuid4()})
        response = self.client.post(url, {"message": "Hi"}, format="json")

        self.assertEqual(response.status_code, 404)


class ExchangeFlowTests(InfoRequestTestCase):
    def test_full_exchange_in_several_rounds(self):
        # Round 1: the vendor asks, the customer answers.
        self.client.force_authenticate(self.vendor)
        self.post("adoption-request-info", {"message": "Do you have a garden?"})
        self.assertEqual(self.current_status(), "INFO_REQUESTED")

        self.client.force_authenticate(self.customer)
        self.post("adoption-reply", {"message": "Yes, a fenced one."})
        self.assertEqual(self.current_status(), "PENDING")

        # Round 2: the vendor asks again and sees the earlier answer.
        self.client.force_authenticate(self.vendor)
        response = self.post("adoption-request-info", {"message": "Any references?"})

        self.assertEqual(response.status_code, 201)
        kinds = [item["kind"] for item in response.json()["info_messages"]]
        self.assertEqual(kinds, ["REQUEST", "REPLY", "REQUEST"])
        bodies = [item["body"] for item in response.json()["info_messages"]]
        self.assertEqual(
            bodies,
            ["Do you have a garden?", "Yes, a fenced one.", "Any references?"],
        )

    def test_customer_sees_the_vendors_question_in_the_reply_response(self):
        self.client.force_authenticate(self.vendor)
        self.post("adoption-request-info", {"message": "Do you have a garden?"})

        self.client.force_authenticate(self.customer)
        response = self.post("adoption-reply", {"message": "Yes."})

        bodies = [item["body"] for item in response.json()["info_messages"]]
        self.assertEqual(bodies, ["Do you have a garden?", "Yes."])