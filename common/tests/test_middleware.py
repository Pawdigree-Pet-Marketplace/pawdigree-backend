import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_authenticated_responses_are_not_stored(api_client):
    response = api_client.get(
        reverse("pet-public-list"), HTTP_AUTHORIZATION="Bearer x"
    )

    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_responses_without_a_token_are_left_alone(api_client):
    response = api_client.get(reverse("pet-public-list"))

    assert response.get("Cache-Control") != "no-store"