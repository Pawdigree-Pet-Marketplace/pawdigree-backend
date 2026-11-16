import pytest
from django.urls import reverse

from audit.models import AuditLog
from pets.tests.test_public_and_admin import make_pet

REASON = "The photos do not match the description."


def approve_url(pet):
    return reverse("pet-admin-approve", kwargs={"pk": pet.pk})


def reject_url(pet):
    return reverse("pet-admin-reject", kwargs={"pk": pet.pk})


@pytest.fixture
def pending(vendor, vendor_business):
    return make_pet(vendor, vendor_business, "Pending Pet")


@pytest.mark.django_db
def test_approve_is_recorded(api_client, admin, pending):
    api_client.force_authenticate(admin)

    response = api_client.post(approve_url(pending))

    assert response.status_code == 200
    entry = AuditLog.objects.get()
    assert entry.action == "pet.approved"
    assert entry.actor == admin
    assert entry.actor_role == admin.role
    assert entry.target_type == "pets.pet"
    assert entry.target_id == str(pending.pk)
    assert entry.details == {"business": str(pending.business_id)}


@pytest.mark.django_db
def test_approving_an_approved_listing_is_not_recorded(
    api_client, admin, vendor, vendor_business
):
    approved = make_pet(vendor, vendor_business, "Done", approved=True)
    api_client.force_authenticate(admin)

    response = api_client.post(approve_url(approved))

    assert response.status_code == 400
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_reject_is_recorded_without_the_reason_text(
    api_client, system_admin, pending
):
    api_client.force_authenticate(system_admin)

    response = api_client.post(
        reject_url(pending), {"reason": REASON}, format="json"
    )

    assert response.status_code == 200
    entry = AuditLog.objects.get()
    assert entry.action == "pet.rejected"
    assert entry.actor == system_admin
    assert entry.target_id == str(pending.pk)
    assert REASON not in str(entry.details)
    pending.refresh_from_db()
    assert pending.rejection_reason == REASON


@pytest.mark.django_db
def test_reject_without_a_reason_is_not_recorded(
    api_client, admin, pending
):
    api_client.force_authenticate(admin)

    response = api_client.post(reject_url(pending), {}, format="json")

    assert response.status_code == 400
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_vendor_cannot_review_and_nothing_is_recorded(
    api_client, vendor, pending
):
    api_client.force_authenticate(vendor)

    assert api_client.post(approve_url(pending)).status_code == 403
    assert (
        api_client.post(
            reject_url(pending), {"reason": REASON}, format="json"
        ).status_code
        == 403
    )
    assert AuditLog.objects.count() == 0
