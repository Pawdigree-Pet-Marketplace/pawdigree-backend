from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from adoptions.models import AdoptionApplication
from pets.models import Pet

LIST_URL = "pet-public-list"


def make_pet(vendor, business, name, **extra):
    fields = {
        "approved": True,
        "age": 6,
        "gender": Pet.Gender.FEMALE,
        "size": Pet.Size.SMALL,
    }
    fields.update(extra)
    return Pet.objects.create(
        vendor=vendor, business=business, name=name, **fields
    )


def names(response):
    data = response.data
    results = data["results"] if isinstance(data, dict) else data
    return [item["name"] for item in results]


def get(api_client, **params):
    return api_client.get(reverse(LIST_URL), params)


@pytest.fixture
def second_customer(db):
    return User.objects.create_user(
        username="secondcustomer",
        email="second@example.com",
        password="TestPassword123!",
        role=User.Role.CUSTOMER,
    )


def apply_for(customer, pet, status_value=AdoptionApplication.Status.PENDING):
    return AdoptionApplication.objects.create(
        customer=customer,
        pet=pet,
        status=status_value,
        home_type="HOUSE",
        previous_pet_experience="NONE",
        message="Please.",
    )


# species, vendor, location


@pytest.mark.django_db
def test_species_filter_accepts_several_values(api_client, vendor, vendor_business):
    make_pet(vendor, vendor_business, "Rex", species="Dog")
    make_pet(vendor, vendor_business, "Tom", species="Cat")
    make_pet(vendor, vendor_business, "Tweety", species="Bird")

    repeated = api_client.get(reverse(LIST_URL) + "?species=dog&species=CAT")
    commas = get(api_client, species="dog,cat")

    assert set(names(repeated)) == {"Rex", "Tom"}
    assert set(names(commas)) == {"Rex", "Tom"}


@pytest.mark.django_db
def test_vendor_filter_matches_part_of_business_name(
    api_client, vendor, vendor_business, another_vendor, another_vendor_business
):
    make_pet(vendor, vendor_business, "Happy Pet")
    make_pet(another_vendor, another_vendor_business, "Other Pet")

    response = get(api_client, vendor="happy")

    assert names(response) == ["Happy Pet"]


@pytest.mark.django_db
def test_location_filter_matches_several_towns(
    api_client, vendor, vendor_business, another_vendor, another_vendor_business
):
    make_pet(vendor, vendor_business, "Kampala Pet")
    make_pet(another_vendor, another_vendor_business, "Entebbe Pet")

    one = get(api_client, location="kampala")
    both = api_client.get(
        reverse(LIST_URL) + "?location=kampala&location=entebbe"
    )

    assert names(one) == ["Kampala Pet"]
    assert set(names(both)) == {"Kampala Pet", "Entebbe Pet"}


# price


@pytest.fixture
def priced_pets(vendor, vendor_business):
    make_pet(
        vendor, vendor_business, "Cheap",
        listing_type=Pet.ListingType.SALE, price=Decimal(100000),
    )
    make_pet(
        vendor, vendor_business, "Pricey",
        listing_type=Pet.ListingType.SALE, price=Decimal(500000),
    )
    make_pet(vendor, vendor_business, "Free", listing_type=Pet.ListingType.ADOPTION)


@pytest.mark.django_db
def test_price_filters_only_match_pets_with_a_price(api_client, priced_pets):
    assert names(get(api_client, price_min="200000")) == ["Pricey"]
    assert names(get(api_client, price_max="200000")) == ["Cheap"]
    assert set(names(get(api_client, price_min="0"))) == {"Cheap", "Pricey"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [{"price_min": "abc"}, {"price_max": "-5"}, {"price_min": "9", "price_max": "1"}],
)
def test_bad_price_values_return_400(api_client, params):
    response = get(api_client, **params)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# sorting


@pytest.mark.django_db
def test_sort_by_price_puts_unpriced_pets_last(api_client, priced_pets):
    assert names(get(api_client, sort="price_asc")) == ["Cheap", "Pricey", "Free"]
    assert names(get(api_client, sort="price_desc")) == ["Pricey", "Cheap", "Free"]


@pytest.mark.django_db
def test_sort_by_age(api_client, vendor, vendor_business):
    make_pet(vendor, vendor_business, "Middle", age=12)
    make_pet(vendor, vendor_business, "Old", age=24)
    make_pet(vendor, vendor_business, "Young", age=3)

    assert names(get(api_client, sort="age_asc")) == ["Young", "Middle", "Old"]
    assert names(get(api_client, sort="age_desc")) == ["Old", "Middle", "Young"]


@pytest.mark.django_db
def test_sort_newest_first(api_client, vendor, vendor_business):
    make_pet(vendor, vendor_business, "First")
    make_pet(vendor, vendor_business, "Second")
    make_pet(vendor, vendor_business, "Third")

    assert names(get(api_client, sort="newest")) == ["Third", "Second", "First"]


@pytest.mark.django_db
def test_sort_popular_counts_each_customer_once(
    api_client, vendor, vendor_business, customer, second_customer
):
    popular = make_pet(vendor, vendor_business, "Popular")
    reapplied = make_pet(vendor, vendor_business, "Reapplied")
    make_pet(vendor, vendor_business, "Ignored")
    apply_for(customer, popular)
    apply_for(second_customer, popular)
    # One customer applying twice must count as one.
    apply_for(customer, reapplied, AdoptionApplication.Status.REJECTED)
    apply_for(customer, reapplied)

    response = get(api_client, sort="popular")

    assert names(response) == ["Popular", "Reapplied", "Ignored"]


@pytest.mark.django_db
def test_invalid_sort_returns_400(api_client):
    response = get(api_client, sort="cheapest")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "sort" in response.data


# page size


@pytest.mark.django_db
def test_page_size_is_respected(api_client, vendor, vendor_business):
    for index in range(3):
        make_pet(vendor, vendor_business, f"Pet {index}")

    response = get(api_client, page_size="2")

    assert response.data["count"] == 3
    assert len(response.data["results"]) == 2


# business name, detail and locations


@pytest.mark.django_db
def test_list_shows_business_name(api_client, vendor, vendor_business):
    make_pet(vendor, vendor_business, "Visible")

    response = get(api_client)

    assert response.data["results"][0]["business_name"] == "Happy Paws"


@pytest.mark.django_db
def test_detail_returns_a_visible_pet(api_client, vendor, vendor_business):
    pet = make_pet(vendor, vendor_business, "Buddy")

    response = api_client.get(reverse("pet-public-detail", args=[pet.pk]))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Buddy"
    assert response.data["business_name"] == "Happy Paws"
    assert "vendor" not in response.data


@pytest.mark.django_db
def test_detail_hides_unapproved_and_deactivated_pets(
    api_client, vendor, vendor_business
):
    unapproved = make_pet(vendor, vendor_business, "Unapproved", approved=False)
    deactivated = make_pet(vendor, vendor_business, "Gone", is_active=False)

    for pet in (unapproved, deactivated):
        response = api_client.get(reverse("pet-public-detail", args=[pet.pk]))
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_locations_lists_towns_of_public_pets_only(
    api_client, vendor, vendor_business, another_vendor, another_vendor_business
):
    make_pet(vendor, vendor_business, "Visible")
    make_pet(another_vendor, another_vendor_business, "Hidden", approved=False)

    response = api_client.get(reverse("pet-public-locations"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == ["Kampala"]

@pytest.mark.django_db
def test_detail_shows_reserved_and_sold_pets_with_their_status(
    api_client, vendor, vendor_business
):
    reserved = make_pet(
        vendor, vendor_business, "Held", adoption_status=Pet.AdoptionStatus.RESERVED
    )
    sold = make_pet(
        vendor, vendor_business, "Gone home", adoption_status=Pet.AdoptionStatus.SOLD
    )

    for pet, expected in ((reserved, "RESERVED"), (sold, "SOLD")):
        response = api_client.get(reverse("pet-public-detail", args=[pet.pk]))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["adoption_status"] == expected


@pytest.mark.django_db
def test_list_still_hides_reserved_and_sold_pets(
    api_client, vendor, vendor_business
):
    make_pet(vendor, vendor_business, "Open")
    make_pet(
        vendor, vendor_business, "Held", adoption_status=Pet.AdoptionStatus.RESERVED
    )
    make_pet(
        vendor, vendor_business, "Gone home", adoption_status=Pet.AdoptionStatus.SOLD
    )

    response = api_client.get(reverse(LIST_URL))

    assert names(response) == ["Open"]


@pytest.mark.django_db
def test_detail_still_hides_an_unapproved_reserved_pet(
    api_client, vendor, vendor_business
):
    pet = make_pet(
        vendor,
        vendor_business,
        "Hidden",
        approved=False,
        adoption_status=Pet.AdoptionStatus.RESERVED,
    )

    response = api_client.get(reverse("pet-public-detail", args=[pet.pk]))

    assert response.status_code == status.HTTP_404_NOT_FOUND
