import pytest
from django.urls import reverse

from pets.tests.test_public_and_admin import make_pet


@pytest.mark.django_db
def test_pending_queue_includes_the_business_name(
    api_client, admin, vendor, vendor_business
):
    make_pet(vendor, vendor_business, "Pending Pet")
    api_client.force_authenticate(admin)

    response = api_client.get(reverse("pet-admin-pending"))

    assert response.status_code == 200
    assert response.data["results"][0]["business_name"] == vendor_business.name
