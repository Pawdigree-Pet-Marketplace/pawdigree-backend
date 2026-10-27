import pytest
from django.urls import reverse
from rest_framework import status

from services.models import Service

URL_NAME = "service-create"


@pytest.mark.django_db
def test_vendor_can_create_service(api_client, vendor, service_data):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse(URL_NAME), service_data, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == service_data["name"]
    assert Service.objects.count() == 1
    assert Service.objects.get().business.vendor == vendor


@pytest.mark.django_db
def test_anonymous_user_cannot_create_service(api_client, service_data):
    response = api_client.post(
        reverse(URL_NAME), service_data, format="json"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert Service.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["customer", "admin", "system_admin"])
def test_only_vendors_can_create_services(
    request, api_client, service_data, role_fixture
):
    user = request.getfixturevalue(role_fixture)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        reverse(URL_NAME), service_data, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Service.objects.count() == 0


@pytest.mark.django_db
def test_vendor_cannot_use_another_vendors_business(
    api_client, vendor, another_vendor, service_data
):
    from businesses.models import Business

    other_business = Business.objects.create(
        vendor=another_vendor,
        name="Other Pet Care",
        description="Pet services",
        contact="+256700654321",
        email="other@example.com",
        address="Another Road",
        city_district="Kampala",
    )
    service_data["business"] = other_business.pk
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse(URL_NAME), service_data, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Service.objects.count() == 0
