import pytest
from django.urls import reverse

from audit.models import AuditLog
from pets.tests.test_public_and_admin import make_pet


def url(pet):
    return reverse("pet-admin-detail", kwargs={"pk": pet.pk})


@pytest.fixture
def pet(vendor, vendor_business):
    return make_pet(vendor, vendor_business, "Buddy", approved=True)


@pytest.mark.django_db
def test_admin_edit_is_recorded(api_client, admin, pet):
    api_client.force_authenticate(admin)

    response = api_client.patch(url(pet), {"name": "Fixed"}, format="json")

    assert response.status_code == 200
    entry = AuditLog.objects.get()
    assert entry.action == "pet.admin_updated"
    assert entry.actor == admin
    assert entry.actor_role == admin.role
    assert entry.target_type == "pets.pet"
    assert entry.target_id == str(pet.pk)
    assert entry.details == {"fields": ["name"]}


@pytest.mark.django_db
def test_system_admin_edit_is_recorded(api_client, system_admin, pet):
    api_client.force_authenticate(system_admin)

    api_client.patch(url(pet), {"name": "Fixed"}, format="json")

    entry = AuditLog.objects.get()
    assert entry.actor == system_admin
    assert entry.actor_role == system_admin.role


@pytest.mark.django_db
def test_rejected_edit_is_not_recorded(api_client, admin, pet):
    api_client.force_authenticate(admin)

    response = api_client.patch(url(pet), {"price": "abc"}, format="json")

    assert response.status_code == 400
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_admin_remove_is_recorded(api_client, admin, pet):
    api_client.force_authenticate(admin)

    response = api_client.delete(url(pet))

    assert response.status_code == 204
    pet.refresh_from_db()
    assert pet.is_active is False
    entry = AuditLog.objects.get()
    assert entry.action == "pet.admin_removed"
    assert entry.actor == admin
    assert entry.target_id == str(pet.pk)
    assert entry.details == {"business": str(pet.business_id)}


@pytest.mark.django_db
def test_removing_an_already_removed_listing_is_not_recorded(
    api_client, admin, pet
):
    api_client.force_authenticate(admin)
    api_client.delete(url(pet))
    AuditLog.objects.all().delete()

    response = api_client.delete(url(pet))

    assert response.status_code == 404
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_vendor_cannot_use_the_admin_route_and_nothing_is_recorded(
    api_client, vendor, pet
):
    api_client.force_authenticate(vendor)

    assert api_client.patch(url(pet), {"name": "X"}, format="json").status_code == 403
    assert api_client.delete(url(pet)).status_code == 403
    assert AuditLog.objects.count() == 0
