import pytest
from rest_framework import status

from pets.models import Pet
from pets.tests.test_bulk_upload import adoption_row, csv_file, sale_row, upload


@pytest.mark.django_db
def test_response_lists_the_ids_of_the_created_pets(
    api_client, vendor, vendor_business
):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client, csv_file(sale_row("Buddy"), adoption_row("Mimi"))
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 2
    assert sorted(response.data["created_ids"]) == sorted(
        Pet.objects.filter(vendor=vendor).values_list("pk", flat=True)
    )


@pytest.mark.django_db
def test_a_failed_row_adds_no_id(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("Good Pet"), sale_row("Bad Pet", price="not-a-number")),
    )

    assert response.data["created"] == 1
    assert len(response.data["failed"]) == 1
    assert response.data["created_ids"] == [Pet.objects.get(name="Good Pet").pk]
