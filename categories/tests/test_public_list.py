from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from categories.models import Category


class PublicCategoryListTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("category-public-list")
        Category.objects.create(name="Pet Toys", kind=Category.Kind.MERCHANDISE)
        Category.objects.create(name="Grooming", kind=Category.Kind.SERVICES)
        Category.objects.create(name="Dogs", kind=Category.Kind.PETS)
        Category.objects.create(
            name="Retired Toys",
            kind=Category.Kind.MERCHANDISE,
            is_active=False,
        )

    def names(self, response):
        return sorted(item["name"] for item in response.data)

    def test_anyone_can_list_active_categories(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.names(response),
            ["Dogs", "Grooming", "Pet Toys"],
        )

    def test_inactive_categories_are_hidden(self):
        response = self.client.get(self.url)

        self.assertNotIn("Retired Toys", self.names(response))

    def test_merchandise_kind_returns_only_merchandise(self):
        response = self.client.get(self.url, {"kind": "merchandise"})

        self.assertEqual(self.names(response), ["Pet Toys"])

    def test_services_kind_returns_only_services(self):
        response = self.client.get(self.url, {"kind": "services"})

        self.assertEqual(self.names(response), ["Grooming"])

    def test_pets_kind_returns_only_pets(self):
        response = self.client.get(self.url, {"kind": "pets"})

        self.assertEqual(self.names(response), ["Dogs"])

    def test_general_kind_is_rejected(self):
        response = self.client.get(self.url, {"kind": "general"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", response.data)

    def test_unknown_kind_returns_400(self):
        response = self.client.get(self.url, {"kind": "furniture"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", response.data)
