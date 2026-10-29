import pytest
from django.urls import reverse
from rest_framework import status

from favourites.models import Favourite
from pets.models import Pet


def detail_url(pet_id):
    return reverse("favourite-detail", args=[pet_id])


def names(response):
    return [item["name"] for item in response.data["results"]]


# Add


@pytest.mark.django_db
def test_customer_can_favourite_a_pet(api_client, customer, pet):
    api_client.force_authenticate(user=customer)

    response = api_client.put(detail_url(pet.pk))

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data == {"pet": pet.pk, "favourite": True}
    assert Favourite.objects.filter(customer=customer, pet=pet).count() == 1


@pytest.mark.django_db
def test_adding_the_same_pet_twice_is_harmless(api_client, customer, pet):
    api_client.force_authenticate(user=customer)
    api_client.put(detail_url(pet.pk))

    response = api_client.put(detail_url(pet.pk))

    assert response.status_code == status.HTTP_200_OK
    assert Favourite.objects.count() == 1


@pytest.mark.django_db
def test_two_customers_can_favourite_the_same_pet(
    api_client, customer, second_customer, pet
):
    for user in (customer, second_customer):
        api_client.force_authenticate(user=user)
        api_client.put(detail_url(pet.pk))

    assert Favourite.objects.filter(pet=pet).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "extra",
    [
        {"approved": False},
        {"is_active": False},
        {"adoption_status": Pet.AdoptionStatus.ADOPTED},
        {"adoption_status": Pet.AdoptionStatus.PENDING},
    ],
)
def test_cannot_favourite_a_pet_that_is_not_publicly_visible(
    api_client, customer, make_pet, extra
):
    hidden = make_pet("Hidden", **extra)
    api_client.force_authenticate(user=customer)

    response = api_client.put(detail_url(hidden.pk))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_unknown_pet_returns_404(api_client, customer):
    api_client.force_authenticate(user=customer)

    response = api_client.put(detail_url(999999))

    assert response.status_code == status.HTTP_404_NOT_FOUND


# Remove


@pytest.mark.django_db
def test_customer_can_remove_a_favourite(api_client, customer, pet):
    Favourite.objects.create(customer=customer, pet=pet)
    api_client.force_authenticate(user=customer)

    response = api_client.delete(detail_url(pet.pk))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_removing_something_not_saved_is_harmless(api_client, customer, pet):
    api_client.force_authenticate(user=customer)

    response = api_client.delete(detail_url(pet.pk))

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_can_remove_a_favourite_whose_pet_is_now_hidden(
    api_client, customer, pet
):
    Favourite.objects.create(customer=customer, pet=pet)
    pet.is_active = False
    pet.save()
    api_client.force_authenticate(user=customer)

    response = api_client.delete(detail_url(pet.pk))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_removing_does_not_touch_another_customers_favourite(
    api_client, customer, second_customer, pet
):
    Favourite.objects.create(customer=second_customer, pet=pet)
    api_client.force_authenticate(user=customer)

    api_client.delete(detail_url(pet.pk))

    assert Favourite.objects.filter(customer=second_customer).count() == 1


# List


@pytest.mark.django_db
def test_list_shows_only_my_favourites_newest_first(
    api_client, customer, second_customer, make_pet
):
    first = make_pet("First")
    second = make_pet("Second")
    other = make_pet("Someone Elses")
    make_pet("Not Saved")
    Favourite.objects.create(customer=customer, pet=first)
    Favourite.objects.create(customer=customer, pet=second)
    Favourite.objects.create(customer=second_customer, pet=other)
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-list"))

    assert response.status_code == status.HTTP_200_OK
    assert names(response) == ["Second", "First"]


@pytest.mark.django_db
def test_list_leaves_out_pets_that_are_no_longer_available(
    api_client, customer, make_pet
):
    visible = make_pet("Visible")
    adopted = make_pet("Adopted")
    deactivated = make_pet("Deactivated")
    for pet in (visible, adopted, deactivated):
        Favourite.objects.create(customer=customer, pet=pet)
    adopted.adoption_status = Pet.AdoptionStatus.ADOPTED
    adopted.save()
    deactivated.is_active = False
    deactivated.save()
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-list"))

    assert names(response) == ["Visible"]


@pytest.mark.django_db
def test_list_has_the_same_shape_as_the_public_pet_list(
    api_client, customer, pet
):
    Favourite.objects.create(customer=customer, pet=pet)
    api_client.force_authenticate(user=customer)

    favourites = api_client.get(reverse("favourite-list")).data["results"][0]
    public = api_client.get(reverse("pet-public-list")).data["results"][0]

    assert set(favourites) == set(public)
    assert "vendor" not in favourites


@pytest.mark.django_db
def test_ids_lists_my_visible_favourites(api_client, customer, make_pet):
    visible = make_pet("Visible")
    hidden = make_pet("Hidden")
    Favourite.objects.create(customer=customer, pet=visible)
    Favourite.objects.create(customer=customer, pet=hidden)
    hidden.is_active = False
    hidden.save()
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-ids"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == [visible.pk]


# Roles


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["vendor", "admin", "system_admin"])
def test_only_customers_can_use_favourites(
    request, api_client, pet, role_fixture
):
    api_client.force_authenticate(user=request.getfixturevalue(role_fixture))

    responses = [
        api_client.get(reverse("favourite-list")),
        api_client.get(reverse("favourite-ids")),
        api_client.put(detail_url(pet.pk)),
        api_client.delete(detail_url(pet.pk)),
    ]

    assert {r.status_code for r in responses} == {status.HTTP_403_FORBIDDEN}
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_anonymous_user_gets_401(api_client, pet):
    responses = [
        api_client.get(reverse("favourite-list")),
        api_client.get(reverse("favourite-ids")),
        api_client.put(detail_url(pet.pk)),
        api_client.delete(detail_url(pet.pk)),
    ]

    assert {r.status_code for r in responses} == {status.HTTP_401_UNAUTHORIZED}