from types import SimpleNamespace

import pytest

from businesses.models import Business
from businesses.serializers import BusinessSerializer


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
            "0700123456",
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