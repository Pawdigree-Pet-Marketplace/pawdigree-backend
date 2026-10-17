import pytest
from django.urls import reverse
from rest_framework import status

from categories.models import Category


def get_results(response):
    """Support paginated and non-paginated API responses."""
    if isinstance(response.data, dict):
        return response.data["results"]

    return response.data


@pytest.mark.django_db
class TestCategoryViews:
    """Tests for category endpoints."""

    def test_admin_can_create_category(self, api_client, admin):
        api_client.force_authenticate(user=admin)

        response = api_client.post(
            reverse("category-list"),
            {
                "name": "Veterinary",
                "description": "Veterinary services",
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Category.objects.filter(name="Veterinary").exists()

    def test_admin_can_update_category(self, api_client, admin):
        category = Category.objects.create(
            name="Veterinary",
            description="Veterinary services",
        )

        api_client.force_authenticate(user=admin)

        response = api_client.patch(
            reverse("category-detail", kwargs={"pk": category.pk}),
            {"name": "Animal Healthcare"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        category.refresh_from_db()

        assert category.name == "Animal Healthcare"
        assert category.slug == "animal-healthcare"

    def test_vendor_cannot_create_category(self, api_client, vendor):
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            reverse("category-list"),
            {
                "name": "Veterinary",
                "description": "Veterinary services",
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_categories_are_hidden_from_vendors(
        self, api_client, vendor
    ):
        Category.objects.create(
            name="Inactive Category",
            is_active=False,
        )
        Category.objects.create(
            name="Active Category",
            is_active=True,
        )

        api_client.force_authenticate(user=vendor)

        response = api_client.get(reverse("category-list"))

        assert response.status_code == status.HTTP_200_OK
        names = {item["name"] for item in get_results(response)}

        assert "Active Category" in names
        assert "Inactive Category" not in names

    def test_admin_can_see_inactive_categories(
        self, api_client, admin
    ):
        Category.objects.create(
            name="Inactive Category",
            is_active=False,
        )

        api_client.force_authenticate(user=admin)

        response = api_client.get(reverse("category-list"))

        assert response.status_code == status.HTTP_200_OK
        names = {item["name"] for item in get_results(response)}

        assert "Inactive Category" in names

    def test_admin_deletes_category_by_deactivating_it(
        self, api_client, admin
    ):
        category = Category.objects.create(name="Veterinary")

        api_client.force_authenticate(user=admin)

        response = api_client.delete(
            reverse("category-detail", kwargs={"pk": category.pk})
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        category.refresh_from_db()

        assert category.is_active is False
        assert Category.objects.filter(pk=category.pk).exists()

    def test_anonymous_user_can_list_active_categories(self, api_client):
        Category.objects.create(
            name="Active Category",
            is_active=True,
        )
        Category.objects.create(
            name="Inactive Category",
            is_active=False,
        )

        response = api_client.get(reverse("category-list"))

        assert response.status_code == status.HTTP_200_OK
        names = {item["name"] for item in get_results(response)}

        assert "Active Category" in names
        assert "Inactive Category" not in names

    def test_anonymous_user_cannot_create_category(self, api_client):
        response = api_client.post(
            reverse("category-list"),
            {
                "name": "Veterinary",
                "description": "Veterinary services",
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_anonymous_user_cannot_update_or_delete_category(self, api_client):
        category = Category.objects.create(
            name="Veterinary",
            description="Veterinary services",
            is_active=True,
        )

        update_response = api_client.patch(
            reverse("category-detail", kwargs={"pk": category.pk}),
            {"name": "Animal Healthcare"},
            format="json",
        )
        delete_response = api_client.delete(
            reverse("category-detail", kwargs={"pk": category.pk})
        )

        assert update_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert delete_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_system_admin_can_create_category(self, api_client, system_admin):
        api_client.force_authenticate(user=system_admin)

        response = api_client.post(
            reverse("category-list"),
            {
                "name": "Veterinary",
                "description": "Veterinary services",
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Category.objects.filter(name="Veterinary").exists()

    def test_system_admin_can_update_category(self, api_client, system_admin):
        category = Category.objects.create(
            name="Veterinary",
            description="Veterinary services",
        )

        api_client.force_authenticate(user=system_admin)

        response = api_client.patch(
            reverse("category-detail", kwargs={"pk": category.pk}),
            {"name": "Animal Healthcare"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        category.refresh_from_db()

        assert category.name == "Animal Healthcare"
        assert category.slug == "animal-healthcare"

    def test_system_admin_can_delete_category(self, api_client, system_admin):
        category = Category.objects.create(
            name="Veterinary",
            description="Veterinary services",
        )

        api_client.force_authenticate(user=system_admin)

        response = api_client.delete(
            reverse("category-detail", kwargs={"pk": category.pk})
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        category.refresh_from_db()

        assert category.is_active is False
        assert Category.objects.filter(pk=category.pk).exists()


    def test_system_admin_can_create_category(self, api_client, system_admin):
        api_client.force_authenticate(user=system_admin)

        response = api_client.post(
            reverse("category-list"),
            {
                "name": "Veterinary",
                "description": "Veterinary services",
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Category.objects.filter(name="Veterinary").exists()

    def test_system_admin_can_update_category(self, api_client, system_admin):
        category = Category.objects.create(
            name="Veterinary",
            description="Veterinary services",
        )

        api_client.force_authenticate(user=system_admin)

        response = api_client.patch(
            reverse("category-detail", kwargs={"pk": category.pk}),
            {"name": "Animal Healthcare"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        category.refresh_from_db()

        assert category.name == "Animal Healthcare"
        assert category.slug == "animal-healthcare"

    def test_system_admin_can_delete_category(self, api_client, system_admin):
        category = Category.objects.create(
            name="Veterinary",
            description="Veterinary services",
        )

        api_client.force_authenticate(user=system_admin)

        response = api_client.delete(
            reverse("category-detail", kwargs={"pk": category.pk})
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        category.refresh_from_db()

        assert category.is_active is False
        assert Category.objects.filter(pk=category.pk).exists()
