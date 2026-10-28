
import pytest
from rest_framework.test import APIClient

from adoptions.models import AdoptionApplication
from pets.models import Pet


@pytest.fixture
def vendor_client(vendor):
    client = APIClient()
    client.force_authenticate(user=vendor)
    return client


@pytest.fixture
def application(pet, customer, application_data):
    data = application_data.copy()
    data.pop("pet")

    return AdoptionApplication.objects.create(
        pet=pet,
        customer=customer,
        **data,
    )


def test_vendor_can_approve_own_pet_application(
    vendor_client, vendor, application, pet
):
    response = vendor_client.patch(
        f"/api/adoptions/applications/{application.application_id}/decision/",
        {
            "status": "APPROVED",
            "decision_reason": "Application approved.",
        },
        format="json",
    )

    assert response.status_code == 200

    application.refresh_from_db()
    pet.refresh_from_db()

    assert application.status == AdoptionApplication.Status.APPROVED
    assert application.decided_by == vendor
    assert application.decided_at is not None
    assert application.decision_reason == "Application approved."
    assert pet.adoption_status == Pet.AdoptionStatus.ADOPTED


def test_vendor_can_reject_own_pet_application(
    vendor_client, application, pet
):
    response = vendor_client.patch(
        f"/api/adoptions/applications/{application.application_id}/decision/",
        {
            "status": "REJECTED",
            "decision_reason": "Application does not meet requirements.",
        },
        format="json",
    )

    assert response.status_code == 200

    application.refresh_from_db()
    pet.refresh_from_db()

    assert application.status == AdoptionApplication.Status.REJECTED
    assert pet.adoption_status == Pet.AdoptionStatus.AVAILABLE


def test_vendor_cannot_decide_another_vendors_application(
    api_client, another_vendor, application
):
    api_client.force_authenticate(user=another_vendor)

    response = api_client.patch(
        f"/api/adoptions/applications/{application.application_id}/decision/",
        {"status": "APPROVED"},
        format="json",
    )

    assert response.status_code == 403
    application.refresh_from_db()
    assert application.status == AdoptionApplication.Status.PENDING


def test_customer_cannot_decide_an_application(
    api_client, customer, application
):
    api_client.force_authenticate(user=customer)

    response = api_client.patch(
        f"/api/adoptions/applications/{application.application_id}/decision/",
        {"status": "REJECTED"},
        format="json",
    )

    assert response.status_code == 403
    application.refresh_from_db()
    assert application.status == AdoptionApplication.Status.PENDING


def test_application_cannot_be_decided_twice(
    vendor_client, application
):
    application.status = AdoptionApplication.Status.REJECTED
    application.save(update_fields=["status"])

    response = vendor_client.patch(
        f"/api/adoptions/applications/{application.application_id}/decision/",
        {"status": "APPROVED"},
        format="json",
    )

    assert response.status_code == 400


def test_invalid_decision_is_rejected(
    vendor_client, application
):
    response = vendor_client.patch(
        f"/api/adoptions/applications/{application.application_id}/decision/",
        {"status": "PENDING"},
        format="json",
    )

    assert response.status_code == 400
