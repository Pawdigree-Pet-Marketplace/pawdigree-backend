import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_authenticated_responses_are_not_stored(api_client):
    response = api_client.get(
        reverse("pet-public-list"), HTTP_AUTHORIZATION="Bearer x"
    )

    assert response["Cache-Control"] == "no-store"
    assert response["Pragma"] == "no-cache"


@pytest.mark.django_db
def test_responses_without_a_token_are_left_alone(api_client):
    response = api_client.get(reverse("pet-public-list"))

    assert response.get("Cache-Control") != "no-store"
    assert response.get("Pragma") is None


@pytest.mark.django_db
def test_auth_responses_are_not_stored_without_a_token(api_client):
    # Login, registration and reset responses carry tokens and codes.
    response = api_client.post(
        reverse("customer-login"),
        {"email": "nobody@example.com", "password": "wrong"},
        format="json",
    )

    assert response["Cache-Control"] == "no-store"
    assert response["Pragma"] == "no-cache"


@pytest.mark.django_db
def test_401_responses_are_not_stored(api_client):
    response = api_client.post(reverse("service-create"), {}, format="json")

    assert response.status_code == 401
    assert response["Cache-Control"] == "no-store"
    assert response["Pragma"] == "no-cache"


@pytest.mark.django_db
def test_403_responses_are_not_stored(api_client, customer):
    api_client.force_authenticate(user=customer)

    response = api_client.post(reverse("service-create"), {}, format="json")

    assert response.status_code == 403
    assert response["Cache-Control"] == "no-store"
    assert response["Pragma"] == "no-cache"