import pytest
from rest_framework.test import APIClient

from countries.views import sort_key

URL = "/api/country-codes/"


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_country_codes_list(client):
    response = client.get(URL)
    assert response.status_code == 200
    uganda = next(c for c in response.json() if c["iso_code"] == "UG")
    assert uganda["country"] == "Uganda"
    assert uganda["dial_code"] == "+256"


@pytest.mark.django_db
def test_country_codes_is_public(client):
    # No login needed, the frontend calls this on the signup page
    response = client.get(URL)
    assert response.status_code == 200


@pytest.mark.django_db
def test_country_codes_response_shape(client):
    data = client.get(URL).json()
    assert len(data) > 0
    for item in data:
        assert set(item.keys()) == {"country", "iso_code", "dial_code"}
        assert item["dial_code"].startswith("+")


@pytest.mark.django_db
def test_country_codes_sorted_by_name(client):
    names = [c["country"] for c in client.get(URL).json()]
    assert names == sorted(names, key=sort_key)


@pytest.mark.django_db
def test_country_codes_accented_names_sorted_correctly(client):
    names = [c["country"] for c in client.get(URL).json()]
    # Åland should be near the start, not after Zimbabwe
    assert names.index("Åland Islands") < names.index("Albania")


@pytest.mark.django_db
def test_country_codes_rejects_post(client):
    response = client.post(URL, {})
    assert response.status_code == 405