import io
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from businesses.models import Business
from businesses.serializers import BusinessSerializer


def make_image_file(filename="test.png", *, size=(10, 10), color=(255, 0, 0)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return SimpleUploadedFile(
        filename,
        buffer.getvalue(),
        content_type="image/png",
    )


@pytest.mark.django_db
class TestBusinessSerializer:
    """Tests for business validation."""

    def test_valid_business_data(self, valid_business_data):
        serializer = BusinessSerializer(data=valid_business_data)

        assert serializer.is_valid(), serializer.errors

    def test_phone_number_spaces_and_hyphens_are_removed(
        self, valid_business_data
    ):
        valid_business_data["contact"] = "+256 700-123-456"

        serializer = BusinessSerializer(data=valid_business_data)

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["contact"] == "+256700123456"

    @pytest.mark.parametrize(
        "phone_number",
        [
            "+25670012345",
            "+2567001234567",
            "invalid-number",
        ],
    )
    def test_invalid_phone_number_is_rejected(
        self, valid_business_data, phone_number
    ):
        valid_business_data["contact"] = phone_number

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "contact" in serializer.errors

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("0700123456", "+256700123456"),
            ("+256 700-123-456", "+256700123456"),
            ("+254712345678", "+254712345678"),
        ],
    )
    def test_contact_is_normalized_to_international_format(
        self, valid_business_data, raw, expected
    ):
        valid_business_data["contact"] = raw

        serializer = BusinessSerializer(data=valid_business_data)

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["contact"] == expected

    def test_business_hours_must_include_all_seven_days(
        self, valid_business_data
    ):
        del valid_business_data["business_hours"]["sunday"]

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "business_hours" in serializer.errors

    def test_business_must_open_before_it_closes(
        self, valid_business_data
    ):
        valid_business_data["business_hours"]["monday"] = {
            "is_open": True,
            "open": "17:00",
            "close": "09:00",
        }

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "business_hours" in serializer.errors

    def test_open_day_requires_opening_and_closing_times(
        self, valid_business_data
    ):
        valid_business_data["business_hours"]["monday"] = {
            "is_open": True,
            "open": "09:00",
        }

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "business_hours" in serializer.errors

    def test_valid_logo_upload_is_accepted(self, valid_business_data):
        valid_business_data["logo"] = make_image_file("logo.png")

        serializer = BusinessSerializer(data=valid_business_data)

        assert serializer.is_valid(), serializer.errors

    def test_invalid_image_content_is_rejected(self, valid_business_data):
        valid_business_data["logo"] = SimpleUploadedFile(
            "logo.png",
            b"not-a-real-image",
            content_type="image/png",
        )

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "logo" in serializer.errors

    def test_unsupported_image_extension_is_rejected(
        self, valid_business_data
    ):
        valid_business_data["logo"] = SimpleUploadedFile(
            "logo.txt",
            b"not-an-image",
            content_type="text/plain",
        )

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "logo" in serializer.errors

    def test_large_image_upload_is_rejected(self, valid_business_data):
        valid_business_data["logo"] = SimpleUploadedFile(
            "logo.png",
            b"A" * (5 * 1024 * 1024 + 1),
            content_type="image/png",
        )

        serializer = BusinessSerializer(data=valid_business_data)

        assert not serializer.is_valid()
        assert "logo" in serializer.errors

    def test_duplicate_business_name_is_rejected(
        self, vendor, valid_business_data
    ):
        Business.objects.create(
            vendor=vendor,
            name="Happy Paws",
            description="Existing business",
            contact="+256700123456",
            email="existing@example.com",
            address="Kampala Road",
            city_district="Kampala",
        )

        valid_business_data["name"] = "happy paws"

        request = SimpleNamespace(user=vendor)
        serializer = BusinessSerializer(
            data=valid_business_data,
            context={"request": request},
        )

        assert not serializer.is_valid()
        assert "name" in serializer.errors