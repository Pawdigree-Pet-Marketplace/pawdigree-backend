import pytest
from django.urls import reverse
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from datetime import timedelta

from favourites.models import Favourite
from pets.models import Pet
from businesses.models import Business
from categories.models import Category
from products.models import Product


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
    
    
def product_url(product_id):
    return reverse("favourite-product-detail", args=[product_id])

# Add

@pytest.mark.django_db
def test_customer_can_favourite_a_product(api_client, customer, product):
    api_client.force_authenticate(user=customer)

    response = api_client.put(product_url(product.pk))

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data == {"product": product.pk, "favourite": True}
    favourite = Favourite.objects.get(customer=customer)
    assert favourite.product == product
    assert favourite.pet is None


@pytest.mark.django_db
def test_adding_the_same_product_twice_is_harmless(api_client, customer, product):
    api_client.force_authenticate(user=customer)
    api_client.put(product_url(product.pk))

    response = api_client.put(product_url(product.pk))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"product": product.pk, "favourite": True}
    assert Favourite.objects.count() == 1


@pytest.mark.django_db
def test_two_customers_can_favourite_the_same_product(
    api_client, customer, second_customer, product
):
    for user in (customer, second_customer):
        api_client.force_authenticate(user=user)
        api_client.put(product_url(product.pk))

    assert Favourite.objects.filter(product=product).count() == 2


@pytest.mark.django_db
def test_request_body_cannot_change_who_owns_the_favourite(
    api_client, customer, second_customer, product
):
    api_client.force_authenticate(user=customer)

    api_client.put(
        product_url(product.pk), {"customer": second_customer.pk}, format="json"
    )

    assert Favourite.objects.get().customer == customer


@pytest.mark.django_db
@pytest.mark.parametrize(
    "extra",
    [
        {"approved": False},
        {"is_active": False},
    ],
)
def test_cannot_favourite_a_product_that_is_not_publicly_visible(
    api_client, customer, make_product, extra
):
    hidden = make_product("Hidden", **extra)
    api_client.force_authenticate(user=customer)

    response = api_client.put(product_url(hidden.pk))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Favourite.objects.count() == 0


def hide_category_inactive(product):
    Category.objects.filter(pk=product.category_id).update(is_active=False)


def hide_category_wrong_kind(product):
    Category.objects.filter(pk=product.category_id).update(kind=Category.Kind.PETS)


def hide_business_inactive(product):
    Business.objects.filter(pk=product.business_id).update(is_active=False)


def hide_business_suspended(product):
    Business.objects.filter(pk=product.business_id).update(
        verification_status=Business.VerificationStatus.SUSPENDED
    )


def hide_business_pending(product):
    Business.objects.filter(pk=product.business_id).update(
        verification_status=Business.VerificationStatus.PENDING
    )


HIDE_THROUGH_RELATIONS = [
    hide_category_inactive,
    hide_category_wrong_kind,
    hide_business_inactive,
    hide_business_suspended,
    hide_business_pending,
]


@pytest.mark.django_db
@pytest.mark.parametrize("hide", HIDE_THROUGH_RELATIONS)
def test_cannot_favourite_a_product_hidden_through_its_business_or_category(
    api_client, customer, make_product, hide
):
    product = make_product("Hidden")
    hide(product)
    api_client.force_authenticate(user=customer)

    response = api_client.put(product_url(product.pk))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_unknown_product_returns_404(api_client, customer):
    api_client.force_authenticate(user=customer)

    response = api_client.put(product_url(999999))

    assert response.status_code == status.HTTP_404_NOT_FOUND


# Remove


@pytest.mark.django_db
def test_customer_can_remove_a_favourite_product(api_client, customer, product):
    Favourite.objects.create(customer=customer, product=product)
    api_client.force_authenticate(user=customer)

    response = api_client.delete(product_url(product.pk))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_removing_a_product_not_saved_is_harmless(api_client, customer, product):
    api_client.force_authenticate(user=customer)

    first = api_client.delete(product_url(product.pk))
    unknown = api_client.delete(product_url(999999))

    assert first.status_code == status.HTTP_204_NO_CONTENT
    assert unknown.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_can_remove_a_favourite_whose_product_is_now_hidden(
    api_client, customer, product
):
    Favourite.objects.create(customer=customer, product=product)
    product.is_active = False
    product.save()
    api_client.force_authenticate(user=customer)

    response = api_client.delete(product_url(product.pk))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_removing_a_product_does_not_touch_another_customers_favourite(
    api_client, customer, second_customer, product
):
    Favourite.objects.create(customer=second_customer, product=product)
    api_client.force_authenticate(user=customer)

    api_client.delete(product_url(product.pk))

    assert Favourite.objects.filter(customer=second_customer).count() == 1


# List


@pytest.mark.django_db
def test_product_list_shows_only_my_favourites_newest_first(
    api_client, customer, second_customer, make_product
):
    first = make_product("First")
    second = make_product("Second")
    other = make_product("Someone Elses")
    make_product("Not Saved")
    now = timezone.now()
    for hours, item in ((2, first), (1, second)):
        favourite = Favourite.objects.create(customer=customer, product=item)
        Favourite.objects.filter(pk=favourite.pk).update(
            created_at=now - timedelta(hours=hours)
        )
    Favourite.objects.create(customer=second_customer, product=other)
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-product-list"))

    assert response.status_code == status.HTTP_200_OK
    assert names(response) == ["Second", "First"]
    assert response.data["count"] == 2


@pytest.mark.django_db
def test_saving_a_product_again_does_not_move_it_to_the_top(
    api_client, customer, make_product
):
    older = make_product("Older")
    newer = make_product("Newer")
    now = timezone.now()
    for hours, item in ((2, older), (1, newer)):
        favourite = Favourite.objects.create(customer=customer, product=item)
        Favourite.objects.filter(pk=favourite.pk).update(
            created_at=now - timedelta(hours=hours)
        )
    api_client.force_authenticate(user=customer)

    api_client.put(product_url(older.pk))
    response = api_client.get(reverse("favourite-product-list"))

    assert names(response) == ["Newer", "Older"]


@pytest.mark.django_db
def test_product_list_leaves_out_products_that_are_no_longer_available(
    api_client, customer, make_product
):
    visible = make_product("Visible")
    unapproved = make_product("Unapproved")
    deactivated = make_product("Deactivated")
    for item in (visible, unapproved, deactivated):
        Favourite.objects.create(customer=customer, product=item)
    unapproved.approved = False
    unapproved.save()
    deactivated.is_active = False
    deactivated.save()
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-product-list"))

    assert names(response) == ["Visible"]


@pytest.mark.django_db
@pytest.mark.parametrize("hide", HIDE_THROUGH_RELATIONS)
def test_product_list_and_ids_drop_products_hidden_through_business_or_category(
    api_client, customer, make_product, hide
):
    product = make_product("Hidden")
    Favourite.objects.create(customer=customer, product=product)
    hide(product)
    api_client.force_authenticate(user=customer)

    listing = api_client.get(reverse("favourite-product-list"))
    ids = api_client.get(reverse("favourite-product-ids"))

    assert names(listing) == []
    assert ids.data == []
    # The row is kept, so it comes back if the product becomes visible again.
    assert Favourite.objects.count() == 1


@pytest.mark.django_db
def test_product_returns_to_the_list_when_visible_again(
    api_client, customer, product
):
    Favourite.objects.create(customer=customer, product=product)
    product.approved = False
    product.save()
    api_client.force_authenticate(user=customer)
    assert names(api_client.get(reverse("favourite-product-list"))) == []

    product.approved = True
    product.save()

    response = api_client.get(reverse("favourite-product-list"))
    assert names(response) == [product.name]


@pytest.mark.django_db
def test_product_list_has_the_same_shape_as_the_public_product_list(
    api_client, customer, product
):
    Favourite.objects.create(customer=customer, product=product)
    api_client.force_authenticate(user=customer)

    favourites = api_client.get(reverse("favourite-product-list")).data["results"][0]
    public = api_client.get(reverse("product-public-list")).data["results"][0]

    assert set(favourites) == set(public)
    assert favourites["id"] == product.pk
    assert favourites["business_name"] == product.business.name
    assert favourites["category_name"] == product.category.name
    assert favourites["main_image"] is None


@pytest.mark.django_db
def test_sold_out_product_is_listed_but_not_available(
    api_client, customer, make_product
):
    sold_out = make_product("Sold out", stock_quantity=0)
    Favourite.objects.create(customer=customer, product=sold_out)
    api_client.force_authenticate(user=customer)

    item = api_client.get(reverse("favourite-product-list")).data["results"][0]

    assert item["is_available"] is False


@pytest.mark.django_db
def test_empty_product_list(api_client, customer):
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-product-list"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"] == []
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_product_list_is_paginated(api_client, customer, make_product):
    now = timezone.now()
    for index in range(13):
        item = make_product(f"Product {index}")
        favourite = Favourite.objects.create(customer=customer, product=item)
        Favourite.objects.filter(pk=favourite.pk).update(
            created_at=now - timedelta(minutes=100 - index)
        )
    api_client.force_authenticate(user=customer)
    url = reverse("favourite-product-list")

    first = api_client.get(url)
    second = api_client.get(url, {"page": 2})
    small = api_client.get(url, {"page_size": 5})

    assert first.data["count"] == 13
    assert len(first.data["results"]) == 12
    assert first.data["next"] is not None
    assert names(second) == ["Product 0"]
    assert len(small.data["results"]) == 5


@pytest.mark.django_db
def test_product_list_does_not_run_more_queries_for_more_products(
    api_client, customer, make_product
):
    api_client.force_authenticate(user=customer)
    url = reverse("favourite-product-list")
    Favourite.objects.create(customer=customer, product=make_product("One"))
    api_client.get(url)  # warm up

    with CaptureQueriesContext(connection) as one:
        api_client.get(url)
    for index in range(6):
        Favourite.objects.create(
            customer=customer, product=make_product(f"More {index}")
        )
    with CaptureQueriesContext(connection) as seven:
        api_client.get(url)

    assert len(seven) == len(one)


@pytest.mark.django_db
def test_product_ids_lists_my_visible_favourites(
    api_client, customer, second_customer, make_product
):
    visible = make_product("Visible")
    hidden = make_product("Hidden")
    theirs = make_product("Theirs")
    Favourite.objects.create(customer=customer, product=visible)
    Favourite.objects.create(customer=customer, product=hidden)
    Favourite.objects.create(customer=second_customer, product=theirs)
    hidden.is_active = False
    hidden.save()
    api_client.force_authenticate(user=customer)

    response = api_client.get(reverse("favourite-product-ids"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == [visible.pk]


@pytest.mark.django_db
def test_heart_on_and_off_flow(api_client, customer, product):
    api_client.force_authenticate(user=customer)
    ids_url = reverse("favourite-product-ids")

    assert api_client.get(ids_url).data == []
    api_client.put(product_url(product.pk))
    assert api_client.get(ids_url).data == [product.pk]
    api_client.delete(product_url(product.pk))
    assert api_client.get(ids_url).data == []


# Pets and products together


@pytest.mark.django_db
def test_pet_and_product_favourites_are_kept_separate(
    api_client, customer, pet, product
):
    api_client.force_authenticate(user=customer)

    api_client.put(detail_url(pet.pk))
    api_client.put(product_url(product.pk))

    assert api_client.get(reverse("favourite-ids")).data == [pet.pk]
    assert api_client.get(reverse("favourite-product-ids")).data == [product.pk]
    assert names(api_client.get(reverse("favourite-list"))) == [pet.name]
    assert names(api_client.get(reverse("favourite-product-list"))) == [product.name]


@pytest.mark.django_db
def test_removing_a_product_leaves_the_pet_favourite(
    api_client, customer, pet, product
):
    Favourite.objects.create(customer=customer, pet=pet)
    Favourite.objects.create(customer=customer, product=product)
    api_client.force_authenticate(user=customer)

    api_client.delete(product_url(product.pk))

    assert Favourite.objects.get().pet == pet


# Roles


PRODUCT_ENDPOINTS = ("list", "ids", "put", "delete")


def product_calls(api_client, product):
    return [
        api_client.get(reverse("favourite-product-list")),
        api_client.get(reverse("favourite-product-ids")),
        api_client.put(product_url(product.pk)),
        api_client.delete(product_url(product.pk)),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["vendor", "admin", "system_admin"])
def test_only_customers_can_use_product_favourites(
    request, api_client, product, role_fixture
):
    api_client.force_authenticate(user=request.getfixturevalue(role_fixture))

    responses = product_calls(api_client, product)

    assert {r.status_code for r in responses} == {status.HTTP_403_FORBIDDEN}
    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_anonymous_user_gets_401_on_product_favourites(api_client, product):
    responses = product_calls(api_client, product)

    assert {r.status_code for r in responses} == {status.HTTP_401_UNAUTHORIZED}


@pytest.mark.django_db
def test_wrong_methods_are_rejected(api_client, customer, product):
    api_client.force_authenticate(user=customer)

    assert api_client.post(product_url(product.pk)).status_code == 405
    assert api_client.patch(product_url(product.pk)).status_code == 405
    assert api_client.post(reverse("favourite-product-list")).status_code == 405
    assert api_client.put(reverse("favourite-product-ids")).status_code == 405


# Database rules


@pytest.mark.django_db
def test_database_needs_exactly_one_target(customer, pet, product):
    with pytest.raises(IntegrityError), transaction.atomic():
        Favourite.objects.create(customer=customer)
    with pytest.raises(IntegrityError), transaction.atomic():
        Favourite.objects.create(customer=customer, pet=pet, product=product)

    assert Favourite.objects.count() == 0


@pytest.mark.django_db
def test_database_rejects_the_same_product_twice(customer, product):
    Favourite.objects.create(customer=customer, product=product)

    with pytest.raises(IntegrityError), transaction.atomic():
        Favourite.objects.create(customer=customer, product=product)


@pytest.mark.django_db
def test_deleting_a_product_removes_its_favourites_only(customer, pet, product):
    Favourite.objects.create(customer=customer, product=product)
    Favourite.objects.create(customer=customer, pet=pet)

    product.delete()

    assert Favourite.objects.get().pet == pet