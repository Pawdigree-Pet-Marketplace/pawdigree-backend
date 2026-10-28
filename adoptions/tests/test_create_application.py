import pytest
from django.urls import reverse
from rest_framework import status

from adoptions.models import AdoptionApplication

URL_NAME = "adoption-application-create"


@pytest.mark.django_db
def test_customer_can_submit_application(
    api_client, customer, pet, application_data
):
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["status"] == AdoptionApplication.Status.PENDING
    assert response.data["pet"] == pet.pk
    assert AdoptionApplication.objects.filter(
        customer=customer, pet=pet
    ).count() == 1


@pytest.mark.django_db
def test_duplicate_open_application_is_rejected(
    api_client, customer, application_data
):
    api_client.force_authenticate(user=customer)
    api_client.post(reverse(URL_NAME), application_data, format="json")

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert AdoptionApplication.objects.count() == 1


@pytest.mark.django_db
def test_customer_can_reapply_after_rejection(
    api_client, customer, pet, application_data
):
    AdoptionApplication.objects.create(
        customer=customer,
        pet=pet,
        status=AdoptionApplication.Status.REJECTED,
        home_type="APARTMENT",
        previous_pet_experience="NONE",
        message="First try.",
    )
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert AdoptionApplication.objects.count() == 2


@pytest.mark.django_db
def test_unapproved_pet_returns_404(
    api_client, customer, pet, application_data
):
    pet.approved = False
    pet.save()
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert AdoptionApplication.objects.count() == 0


@pytest.mark.django_db
def test_deactivated_pet_returns_404(
    api_client, customer, pet, application_data
):
    pet.is_active = False
    pet.save()
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_unknown_pet_returns_404(api_client, customer, application_data):
    application_data["pet"] = 999999
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["vendor", "admin", "system_admin"])
def test_only_customers_can_submit(
    request, api_client, application_data, role_fixture
):
    api_client.force_authenticate(user=request.getfixturevalue(role_fixture))

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert AdoptionApplication.objects.count() == 0


@pytest.mark.django_db
def test_anonymous_user_gets_401(api_client, application_data):
    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_invalid_home_type_returns_400(
    api_client, customer, application_data
):
    application_data["home_type"] = "CASTLE"
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_missing_message_returns_400(api_client, customer, application_data):
    del application_data["message"]
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST