import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError

from adoptions.models import AdoptionApplication
from adoptions.services import decide_adoption_application
from pets.models import Pet

URL_NAME = "adoption-application-create"


def make_sale(pet):
    Pet.objects.filter(pk=pet.pk).update(
        listing_type=Pet.ListingType.SALE,
        price=50000,
    )
    pet.refresh_from_db()


@pytest.mark.django_db
def test_application_for_a_sale_listing_is_refused(
    api_client, customer, pet, application_data
):
    make_sale(pet)
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "for sale" in str(response.data["pet"])
    assert AdoptionApplication.objects.count() == 0


@pytest.mark.django_db
def test_adoption_listing_still_accepts_applications(
    api_client, customer, pet, application_data
):
    assert pet.listing_type == Pet.ListingType.ADOPTION
    api_client.force_authenticate(user=customer)

    response = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_approving_an_application_on_a_sale_listing_fails(
    api_client, customer, vendor, pet, application_data
):
    api_client.force_authenticate(user=customer)
    created = api_client.post(
        reverse(URL_NAME), application_data, format="json"
    )
    assert created.status_code == status.HTTP_201_CREATED
    application = AdoptionApplication.objects.get()

    make_sale(pet)

    with pytest.raises(ValidationError):
        decide_adoption_application(
            application.pk,
            vendor,
            AdoptionApplication.Status.APPROVED,
        )

    pet.refresh_from_db()
    application.refresh_from_db()
    assert pet.adoption_status == Pet.AdoptionStatus.AVAILABLE
    assert application.status == AdoptionApplication.Status.PENDING
