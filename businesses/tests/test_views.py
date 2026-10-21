import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from PIL import Image, PngImagePlugin
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from businesses.models import Business


def make_uploaded_image(filename="test.png", format_name="PNG", color=(255, 0, 0)):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(buffer, format=format_name)
    return SimpleUploadedFile(
        filename,
        buffer.getvalue(),
        content_type=f"image/{format_name.lower()}",
    )


def get_results(response):
    """Support paginated and non-paginated API responses."""
    if isinstance(response.data, dict):
        return response.data["results"]

    return response.data


def test_business_registration_schema_uses_binary_file_uploads():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    business_schema = schema["components"]["schemas"]["Business"]

    business_hours = business_schema["properties"]["business_hours"]
    assert business_hours["type"] == "object"
    assert set(business_hours["properties"]) == {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
    assert "is_open" in business_hours["properties"]["monday"]["properties"]
    assert "id" in business_schema["properties"]
    assert "verification_status" in business_schema["properties"]

    for field_name in ("logo", "cover_image"):
        field = business_schema["properties"][field_name]
        assert field["type"] == "string"
        assert field["format"] == "binary"

    request_body = schema["paths"]["/api/auth/businesses/register/"]["post"][
        "requestBody"
    ]["content"]
    assert "multipart/form-data" in request_body

    multipart_schema = request_body["multipart/form-data"]["schema"]
    assert "$ref" in multipart_schema
    request_schema_name = multipart_schema["$ref"].split("/")[-1]
    request_schema = schema["components"]["schemas"][request_schema_name]
    assert "id" not in request_schema["properties"]
    assert "verification_status" not in request_schema["properties"]


@pytest.mark.django_db
class TestBusinessViews:
    """Tests for vendor business endpoints."""

    def test_vendor_can_create_business(
        self, api_client, vendor, valid_business_data
    ):
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Business.objects.filter(
            vendor=vendor,
            name="New Happy Paws",
        ).exists()

    @pytest.mark.parametrize(
        "filename, format_name",
        [("logo.jpg", "JPEG"), ("logo.png", "PNG"), ("logo.webp", "WEBP")],
    )
    def test_vendor_can_create_business_with_supported_image(
        self, api_client, vendor, valid_business_data, filename, format_name
    ):
        api_client.force_authenticate(user=vendor)
        payload = {
            **valid_business_data,
            "business_hours": json.dumps(valid_business_data["business_hours"]),
            "logo": make_uploaded_image(
                filename=filename,
                format_name=format_name,
            ),
        }

        response = api_client.post(
            reverse("business-list"),
            payload,
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Business.objects.filter(
            vendor=vendor,
            name="New Happy Paws",
        ).exists()

    def test_invalid_image_is_rejected_via_business_api(
        self, api_client, vendor, valid_business_data
    ):
        api_client.force_authenticate(user=vendor)
        payload = {
            **valid_business_data,
            "business_hours": json.dumps(valid_business_data["business_hours"]),
            "logo": SimpleUploadedFile(
                "logo.png",
                b"not-a-real-image",
                content_type="image/png",
            ),
        }

        response = api_client.post(
            reverse("business-list"),
            payload,
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "logo" in response.data
        assert "valid image" in str(response.data["logo"]).lower()

    def test_large_image_is_rejected_via_business_api(
        self, api_client, vendor, valid_business_data
    ):
        api_client.force_authenticate(user=vendor)

        large_image_buffer = io.BytesIO()
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("comment", "A" * (6 * 1024 * 1024))
        Image.new("RGB", (10, 10), (255, 0, 0)).save(
            large_image_buffer,
            format="PNG",
            pnginfo=png_info,
        )
        payload = {
            **valid_business_data,
            "business_hours": json.dumps(valid_business_data["business_hours"]),
            "logo": SimpleUploadedFile(
                "logo-large.png",
                large_image_buffer.getvalue(),
                content_type="image/png",
            ),
        }

        response = api_client.post(
            reverse("business-list"),
            payload,
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "logo" in response.data
        assert "5 mb" in str(response.data["logo"]).lower()

    def test_vendor_can_update_own_business(
        self, api_client, vendor, business
    ):
        api_client.force_authenticate(user=vendor)

        response = api_client.patch(
            reverse(
                "business-detail",
                kwargs={"pk": business.pk},
            ),
            {
                "name": "Happy Paws Updated",
                "description": "Updated pet care services",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        business.refresh_from_db()

        assert business.name == "Happy Paws Updated"
        assert business.description == "Updated pet care services"

    def test_vendor_can_only_see_own_businesses(
        self, api_client, vendor, another_vendor, business
    ):
        Business.objects.create(
            vendor=another_vendor,
            name="Another Business",
            description="Other vendor's business",
            contact="+256700123456",
            email="anotherbusiness@example.com",
            address="Entebbe Road",
            city_district="Wakiso",
        )

        api_client.force_authenticate(user=vendor)

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(get_results(response)) == 1
        assert get_results(response)[0]["name"] == "Happy Paws"

    def test_vendor_cannot_access_another_vendors_business(
        self, api_client, vendor, another_vendor
    ):
        other_business = Business.objects.create(
            vendor=another_vendor,
            name="Another Business",
            description="Other vendor's business",
            contact="+256700123456",
            email="anotherbusiness@example.com",
            address="Entebbe Road",
            city_district="Wakiso",
        )

        api_client.force_authenticate(user=vendor)

        response = api_client.get(
            reverse(
                "business-detail",
                kwargs={"pk": other_business.pk},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_customer_cannot_create_business(
        self, api_client, customer, valid_business_data
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_customer_cannot_list_vendor_businesses(
        self, api_client, customer, business
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_create_business(
        self, api_client, admin, valid_business_data
    ):
        api_client.force_authenticate(user=admin)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_list_vendor_businesses(
        self, api_client, admin, business
    ):
        api_client.force_authenticate(user=admin)

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_customer_cannot_access_vendor_business_detail(
        self, api_client, customer, business
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.get(
            reverse("business-detail", kwargs={"pk": business.pk})
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_vendor_cannot_patch_another_vendors_business(
        self, api_client, vendor, another_vendor
    ):
        other_business = Business.objects.create(
            vendor=another_vendor,
            name="Another Business",
            description="Other vendor's business",
            contact="+256700123456",
            email="anotherbusiness@example.com",
            address="Entebbe Road",
            city_district="Wakiso",
        )

        api_client.force_authenticate(user=vendor)

        response = api_client.patch(
            reverse("business-detail", kwargs={"pk": other_business.pk}),
            {"name": "Should Not Update"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_user_cannot_list_businesses(self, api_client):
        response = api_client.get(reverse("business-list"))

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_inactive_vendor_cannot_access_business_workspace(
        self, api_client, vendor
    ):
        vendor.is_active = False
        vendor.save(update_fields=["is_active"])

        refresh = RefreshToken.for_user(vendor)
        api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        response = api_client.get(reverse("business-list"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_system_admin_cannot_create_business(
        self, api_client, system_admin, valid_business_data
    ):
        api_client.force_authenticate(user=system_admin)

        response = api_client.post(
            reverse("business-list"),
            valid_business_data,
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Business.objects.filter(name="New Happy Paws").exists()

    def test_system_admin_cannot_access_vendor_business_detail(
        self, api_client, system_admin, business
    ):
        api_client.force_authenticate(user=system_admin)

        response = api_client.get(
            reverse("business-detail", kwargs={"pk": business.pk})
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_vendor_response_is_saved(
        self, api_client, vendor, business
    ):
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            reverse(
                "business-vendor-response",
                kwargs={"pk": business.pk},
            ),
            {"vendor_response": "I corrected the requested documents."},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        business.refresh_from_db()
        assert business.vendor_response == (
            "I corrected the requested documents."
        )

    def test_vendor_cannot_respond_to_another_business(
        self, api_client, vendor, another_vendor
    ):
        other_business = Business.objects.create(
            vendor=another_vendor,
            name="Other Business",
            description="Other vendor's business",
            contact="+256700123456",
            email="other@example.com",
            address="Entebbe Road",
            city_district="Wakiso",
        )
        api_client.force_authenticate(user=vendor)

        response = api_client.post(
            reverse(
                "business-vendor-response",
                kwargs={"pk": other_business.pk},
            ),
            {"vendor_response": "My response"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_business_update_resubmits_for_review(
        self, api_client, vendor, business
    ):
        business.verification_status = Business.VerificationStatus.APPROVED
        business.save(update_fields=["verification_status"])
        api_client.force_authenticate(user=vendor)

        response = api_client.patch(
            reverse("business-detail", kwargs={"pk": business.pk}),
            {"description": "Updated business description"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        business.refresh_from_db()
        assert business.verification_status == (
            Business.VerificationStatus.PENDING
        )
        assert business.reviewed_at is None


@pytest.mark.django_db
class TestPublicBusinessListing:
    def test_public_listing_returns_only_approved_active_businesses(
        self, api_client, business, another_vendor
    ):
        business.verification_status = Business.VerificationStatus.APPROVED
        business.save()

        inactive = Business.objects.create(
            vendor=another_vendor,
            name="Inactive Paws",
            description="Inactive business",
            contact="+256700123457",
            email="inactive@example.com",
            address="Kampala Road",
            city_district="Kampala",
            verification_status=Business.VerificationStatus.APPROVED,
            is_active=False,
        )

        pending = Business.objects.create(
            vendor=another_vendor,
            name="Pending Paws",
            description="Pending business",
            contact="+256700123458",
            email="pending@example.com",
            address="Kampala Road",
            city_district="Kampala",
            verification_status=Business.VerificationStatus.PENDING,
        )

        response = api_client.get(reverse("business-public-list"))

        assert response.status_code == status.HTTP_200_OK
        results = get_results(response)
        result_ids = {str(item["id"]) for item in results}

        assert result_ids == {str(business.id)}
        assert str(inactive.id) not in result_ids
        assert str(pending.id) not in result_ids

    def test_public_listing_does_not_require_authentication(
        self, api_client, business
    ):
        business.verification_status = Business.VerificationStatus.APPROVED
        business.save()

        response = api_client.get(reverse("business-public-list"))

        assert response.status_code == status.HTTP_200_OK
        assert str(business.id) in {
            str(item["id"]) for item in get_results(response)
        }

    def test_public_listing_excludes_unapproved_businesses(
        self, api_client, business
    ):
        response = api_client.get(reverse("business-public-list"))

        assert response.status_code == status.HTTP_200_OK
        assert str(business.id) not in {
            str(item["id"]) for item in get_results(response)
        }
