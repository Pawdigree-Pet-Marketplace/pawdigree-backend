from rest_framework import status

from accounts.models import User


STATUS_URL = "/api/adoptions/my-applications/"
CREATE_URL = "/api/adoptions/applications/"


def test_customer_can_view_their_own_adoption_applications(
    api_client, customer, pet, application_data
):
    api_client.force_authenticate(user=customer)

    create_response = api_client.post(
        CREATE_URL,
        application_data,
        format="json",
    )

    assert create_response.status_code == status.HTTP_201_CREATED

    response = api_client.get(STATUS_URL)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["application_id"] == create_response.data["application_id"]
    assert response.data[0]["status"] == "PENDING"


def test_customer_cannot_view_another_customers_applications(
    api_client, customer, pet, application_data
):
    second_customer = User.objects.create_user(
        username="secondcustomer",
        email="secondcustomer@example.com",
        password="TestPassword123!",
        role=User.Role.CUSTOMER,
    )

    # The first customer submits an application.
    api_client.force_authenticate(user=customer)
    create_response = api_client.post(
        CREATE_URL,
        application_data,
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # The second customer should not see the first customer's application.
    api_client.force_authenticate(user=second_customer)
    response = api_client.get(STATUS_URL)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == []


def test_vendor_cannot_view_customer_adoption_status(
    api_client, vendor
):
    api_client.force_authenticate(user=vendor)

    response = api_client.get(STATUS_URL)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_unauthenticated_user_cannot_view_adoption_status(api_client):
    response = api_client.get(STATUS_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED