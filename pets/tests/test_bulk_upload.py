import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from businesses.models import Business
from pets.models import Pet
from pets.views import BULK_COLUMNS

HEADER = ",".join(BULK_COLUMNS)


def csv_file(*rows, header=HEADER, name="pets.csv", encoding="utf-8"):
    content = "\n".join([header, *rows]) + "\n"
    return SimpleUploadedFile(
        name,
        content.encode(encoding),
        content_type="text/csv",
    )


def upload(api_client, file):
    return api_client.post(
        reverse("pet-bulk-upload"),
        {"file": file},
        format="multipart",
    )


def sale_row(name="Buddy", business_id="", price="450000"):
    return f"{business_id},SALE,{name},Dog,Labrador,12,MALE,MEDIUM,Friendly,{price}"


def adoption_row(name="Mimi", business_id="", price=""):
    return f"{business_id},ADOPTION,{name},Cat,,6,FEMALE,SMALL,Needs a home,{price}"


@pytest.mark.django_db
def test_vendor_can_bulk_upload_valid_rows(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("Buddy"), adoption_row("Mimi")),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 2
    assert response.data["failed"] == []

    pets = Pet.objects.filter(vendor=vendor)

    assert pets.count() == 2
    assert all(pet.business_id == vendor_business.pk for pet in pets)
    assert all(pet.approved is False for pet in pets)


@pytest.mark.django_db
def test_bulk_uploaded_pets_appear_in_pending_review(
    api_client, vendor, vendor_business
):
    api_client.force_authenticate(user=vendor)

    upload(api_client, csv_file(sale_row("Buddy"), adoption_row("Mimi")))

    assert Pet.objects.pending_review().count() == 2


@pytest.mark.django_db
def test_sale_row_without_price_fails_but_other_rows_are_created(
    api_client, vendor, vendor_business
):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(
            sale_row("Good Sale"),
            sale_row("No Price", price=""),
            adoption_row("Good Adoption"),
        ),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 2
    assert len(response.data["failed"]) == 1
    assert response.data["failed"][0]["row"] == 3
    assert "price" in response.data["failed"][0]["errors"]
    assert not Pet.objects.filter(name="No Price").exists()


@pytest.mark.django_db
def test_adoption_row_with_price_fails(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(adoption_row("Priced Adoption", price="100000")),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 0
    assert response.data["failed"][0]["row"] == 2
    assert "price" in response.data["failed"][0]["errors"]
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_row_with_another_vendors_business_fails(
    api_client, vendor, vendor_business, another_vendor_business
):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(
            sale_row("Mine"),
            sale_row("Not Mine", business_id=another_vendor_business.pk),
        ),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 1
    assert response.data["failed"][0]["row"] == 3
    assert "business" in response.data["failed"][0]["errors"]
    assert not Pet.objects.filter(name="Not Mine").exists()


@pytest.mark.django_db
def test_unknown_business_id_fails(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("Ghost", business_id=999999)),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 0
    assert "business" in response.data["failed"][0]["errors"]


@pytest.mark.django_db
def test_blank_business_id_fails_when_vendor_has_several_businesses(
    api_client, vendor, vendor_business
):
    Business.objects.create(
        vendor=vendor,
        name="Second Paws",
        description="Pet care services",
        contact="+256700123458",
        email="second-paws@example.com",
        address="Jinja Road",
        city_district="Jinja",
    )
    api_client.force_authenticate(user=vendor)

    response = upload(api_client, csv_file(sale_row("Unclear")))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 0
    assert "business" in response.data["failed"][0]["errors"]


@pytest.mark.django_db
def test_explicit_business_id_works_when_vendor_has_several_businesses(
    api_client, vendor, vendor_business
):
    second = Business.objects.create(
        vendor=vendor,
        name="Second Paws",
        description="Pet care services",
        contact="+256700123458",
        email="second-paws@example.com",
        address="Jinja Road",
        city_district="Jinja",
    )
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("Chosen", business_id=second.pk)),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 1
    assert Pet.objects.get(name="Chosen").business_id == second.pk


@pytest.mark.django_db
def test_enum_values_are_uppercased_and_headers_are_normalised(
    api_client, vendor, vendor_business
):
    api_client.force_authenticate(user=vendor)
    header = " Business_ID ,Listing_Type,Name,Species,Breed,Age,Gender,Size,Description,Price"

    response = upload(
        api_client,
        csv_file(
            ",sale,Lower Case,Dog,Mixed,12,male,medium,Fine,300000",
            header=header,
        ),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 1

    pet = Pet.objects.get(name="Lower Case")

    assert pet.listing_type == Pet.ListingType.SALE
    assert pet.gender == Pet.Gender.MALE
    assert pet.size == Pet.Size.MEDIUM


@pytest.mark.django_db
def test_file_saved_with_excel_bom_is_accepted(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("Excel Pet"), encoding="utf-8-sig"),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 1


@pytest.mark.django_db
def test_completely_empty_rows_are_skipped(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("First"), ",,,,,,,,,", sale_row("Second")),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 2
    assert response.data["failed"] == []


@pytest.mark.django_db
def test_failed_row_numbers_match_the_spreadsheet(
    api_client, vendor, vendor_business
):
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(
            sale_row("One"),
            sale_row("Two"),
            sale_row("Bad", price=""),
        ),
    )

    assert response.data["created"] == 2
    assert [item["row"] for item in response.data["failed"]] == [4]


@pytest.mark.django_db
def test_wrong_file_type_is_rejected(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)
    file = SimpleUploadedFile("pets.txt", b"hello", content_type="text/plain")

    response = upload(api_client, file)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_request_without_a_file_is_rejected(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(
        reverse("pet-bulk-upload"),
        {},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data


@pytest.mark.django_db
def test_missing_required_column_is_rejected(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)
    header = "business_id,listing_type,name,species,age,gender,description,price"

    response = upload(
        api_client,
        csv_file(",SALE,Buddy,Dog,12,MALE,Friendly,450000", header=header),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "size" in str(response.data["file"])
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_file_with_only_a_header_is_rejected(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)

    response = upload(api_client, csv_file())

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data


@pytest.mark.django_db
def test_file_that_is_not_utf8_is_rejected(api_client, vendor, vendor_business):
    api_client.force_authenticate(user=vendor)
    file = SimpleUploadedFile(
        "pets.csv",
        b"\xff\xfe\x00bad",
        content_type="text/csv",
    )

    response = upload(api_client, file)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data


@pytest.mark.django_db
def test_file_with_too_many_rows_is_rejected(
    api_client, vendor, vendor_business, monkeypatch
):
    monkeypatch.setattr("pets.views.BULK_MAX_ROWS", 2)
    api_client.force_authenticate(user=vendor)

    response = upload(
        api_client,
        csv_file(sale_row("One"), sale_row("Two"), sale_row("Three")),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_file_over_the_size_limit_is_rejected(
    api_client, vendor, vendor_business, monkeypatch
):
    monkeypatch.setattr("pets.views.BULK_MAX_FILE_BYTES", 10)
    api_client.force_authenticate(user=vendor)

    response = upload(api_client, csv_file(sale_row("Big")))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_customer_cannot_bulk_upload(api_client, customer, vendor_business):
    api_client.force_authenticate(user=customer)

    response = upload(api_client, csv_file(sale_row("Nope")))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_system_admin_cannot_bulk_upload(api_client, system_admin, vendor_business):
    api_client.force_authenticate(user=system_admin)

    response = upload(api_client, csv_file(sale_row("Nope")))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_unauthenticated_user_cannot_bulk_upload(api_client, vendor_business):
    response = upload(api_client, csv_file(sale_row("Nope")))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert Pet.objects.count() == 0


@pytest.mark.django_db
def test_template_downloads_without_a_token(api_client):
    response = api_client.get(reverse("pet-bulk-template"))

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"].startswith("text/csv")
    assert "pet_listings_template.csv" in response["Content-Disposition"]

    lines = response.content.decode().splitlines()

    assert lines[0] == HEADER
    assert len(lines) == 3


@pytest.mark.django_db
def test_template_example_rows_upload_cleanly(api_client, vendor, vendor_business):
    template = api_client.get(reverse("pet-bulk-template"))
    file = SimpleUploadedFile(
        "template.csv",
        template.content,
        content_type="text/csv",
    )
    api_client.force_authenticate(user=vendor)

    response = upload(api_client, file)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["created"] == 2
    assert response.data["failed"] == []
