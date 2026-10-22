import pytest

from pets.models import Pet

URL = "/api/pets/public/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_pet(vendor, vendor_business):
    def _make_pet(**overrides):
        data = {
            "vendor": vendor,
            "business": vendor_business,
            "name": "Buddy",
            "species": "dog",
            "breed": "Labrador",
            "age": 12,
            "gender": "MALE",
            "size": "MEDIUM",
            "description": "Friendly and calm.",
            "approved": True,
            "is_active": True,
            "adoption_status": "AVAILABLE",
            "listing_type": "ADOPTION",
        }
        data.update(overrides)
        return Pet.objects.create(**data)

    return _make_pet


def names(response):
    return {item["name"] for item in response.json()["results"]}


def test_public_list_works_anonymously(api_client, make_pet):
    make_pet(name="Rex")
    response = api_client.get(URL)
    assert response.status_code == 200
    assert names(response) == {"Rex"}


@pytest.mark.parametrize(
    "overrides, term",
    [
        ({"name": "Biscuit"}, "biscu"),
        ({"breed": "Siberian Husky"}, "HUSKY"),
        ({"species": "rabbit"}, "rabb"),
        ({"description": "Loves long walks"}, "WALKS"),
    ],
)
def test_search_matches_each_field(api_client, make_pet, overrides, term):
    make_pet(name="Other", breed="Poodle", species="cat", description="Quiet")
    target = make_pet(**{"name": "Target", **overrides})

    response = api_client.get(URL, {"search": term})
    assert response.status_code == 200
    assert names(response) == {target.name}


def test_blank_search_is_ignored(api_client, make_pet):
    make_pet(name="Rex")
    response = api_client.get(URL, {"search": "   "})
    assert names(response) == {"Rex"}


def test_breed_filter_is_exact_and_case_insensitive(api_client, make_pet):
    make_pet(name="A", breed="Husky")
    make_pet(name="B", breed="Siberian Husky")
    response = api_client.get(URL, {"breed": "husky"})
    assert names(response) == {"A"}


def test_gender_filter_is_case_insensitive(api_client, make_pet):
    make_pet(name="Boy", gender="MALE")
    make_pet(name="Girl", gender="FEMALE")
    response = api_client.get(URL, {"gender": "female"})
    assert names(response) == {"Girl"}


def test_listing_type_filter(api_client, make_pet):
    make_pet(name="Adopt", listing_type="ADOPTION")
    make_pet(name="Sell", listing_type="SALE", price="100.00")
    response = api_client.get(URL, {"listing_type": "sale"})
    assert names(response) == {"Sell"}


def test_age_range_is_inclusive(api_client, make_pet):
    make_pet(name="Young", age=2)
    make_pet(name="Mid", age=12)
    make_pet(name="Old", age=36)

    response = api_client.get(URL, {"age_min": 2, "age_max": 12})
    assert names(response) == {"Young", "Mid"}

    response = api_client.get(URL, {"age_min": 13})
    assert names(response) == {"Old"}

    response = api_client.get(URL, {"age_max": 2})
    assert names(response) == {"Young"}


def test_filters_combine(api_client, make_pet):
    make_pet(name="Match", breed="Husky", gender="MALE", age=10)
    make_pet(name="WrongGender", breed="Husky", gender="FEMALE", age=10)
    make_pet(name="WrongAge", breed="Husky", gender="MALE", age=40)
    make_pet(name="WrongBreed", breed="Poodle", gender="MALE", age=10)

    response = api_client.get(
        URL,
        {"breed": "husky", "gender": "MALE", "age_max": 12},
    )
    assert names(response) == {"Match"}


def test_hidden_pets_never_appear_through_filters(api_client, make_pet):
    make_pet(name="Visible", breed="Husky")
    make_pet(name="Deactivated", breed="Husky", is_active=False)
    make_pet(name="Unapproved", breed="Husky", approved=False)
    make_pet(name="Adopted", breed="Husky", adoption_status="ADOPTED")

    assert names(api_client.get(URL, {"breed": "Husky"})) == {"Visible"}
    assert names(api_client.get(URL, {"search": "husky"})) == {"Visible"}


@pytest.mark.parametrize(
    "params, field",
    [
        ({"gender": "robot"}, "gender"),
        ({"listing_type": "rent"}, "listing_type"),
        ({"age_min": "abc"}, "age_min"),
        ({"age_max": "-3"}, "age_max"),
        ({"age_min": "1.5"}, "age_min"),
    ],
)
def test_invalid_values_return_400(api_client, make_pet, params, field):
    make_pet()
    response = api_client.get(URL, params)
    assert response.status_code == 400
    assert field in response.json()


def test_age_min_greater_than_age_max_returns_400(api_client, make_pet):
    make_pet()
    response = api_client.get(URL, {"age_min": 20, "age_max": 5})
    assert response.status_code == 400
    assert "age_min" in response.json()


def test_pagination_keeps_filters(api_client, make_pet):
    for i in range(21):
        make_pet(name=f"Husky {i}", breed="Husky")
    make_pet(name="Poodle", breed="Poodle")

    response = api_client.get(URL, {"breed": "husky"})
    body = response.json()
    assert body["count"] == 21
    assert len(body["results"]) == 20
    assert "breed=husky" in body["next"]

    page_two = api_client.get(URL, {"breed": "husky", "page": 2})
    assert len(page_two.json()["results"]) == 1