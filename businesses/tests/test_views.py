import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from businesses.models import Business


def get_results(response):
    """Support paginated and non-paginated API responses."""
    if isinstance(response.data, dict):
        return response.data["results"]

    return response.data


@pytest.mark.django_db
class TestBusinessViews:
    """Tests for vendor business endpoints."""

    def test_vendor_can_create_business(
        self, api_client, vendor, valid_business_data
    ):
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Business.objects.filter(
            vendor=vendor,
            name="New Happy Paws",
        ).exists()

    def test_vendor_can_update_own_business(
        self, api_client, vendor, business
    ):
        api_client.force_authenticate(user=vendor)

        response = api_client.patch(
            reverse(
                "business-detail",
                kwargs={"pk": business.pk},
            ),
            {
                "name": "Happy Paws Updated",
                "description": "Updated pet care services",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        business.refresh_from_db()

        assert business.name == "Happy Paws Updated"
        assert business.description == "Updated pet care services"

    def test_vendor_can_only_see_own_businesses(
        self, api_client, vendor, another_vendor, business
    ):
        Business.objects.create(
            vendor=another_vendor,
            name="Another Business",
            description="Other vendor's business",
            contact="+256700123456",
            email="anotherbusiness@example.com",
            address="Entebbe Road",
            city_district="Wakiso",
        )

        api_client.force_authenticate(user=vendor)

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(get_results(response)) == 1
        assert get_results(response)[0]["name"] == "Happy Paws"

    def test_vendor_cannot_access_another_vendors_business(
        self, api_client, vendor, another_vendor
    ):
        other_business = Business.objects.create(
            vendor=another_vendor,
            name="Another Business",
            description="Other vendor's business",
            contact="+256700123456",
            email="anotherbusiness@example.com",
            address="Entebbe Road",
            city_district="Wakiso",
        )

        api_client.force_authenticate(user=vendor)

        response = api_client.get(
            reverse(
                "business-detail",
                kwargs={"pk": other_business.pk},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_customer_cannot_create_business(
        self, api_client, customer, valid_business_data
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_create_business(
        self, api_client, admin, valid_business_data
    ):
        api_client.force_authenticate(user=admin)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_list_vendor_businesses(
        self, api_client, admin, business
    ):
        api_client.force_authenticate(user=admin)

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_user_cannot_list_businesses(self, api_client):
        response = api_client.get(reverse("business-list"))

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_inactive_vendor_cannot_access_business_workspace(
        self, api_client, vendor
    ):
        vendor.is_active = False
        vendor.save(update_fields=["is_active"])

        refresh = RefreshToken.for_user(vendor)
        api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED