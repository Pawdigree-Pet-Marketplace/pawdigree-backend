import re
from datetime import time

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from categories.models import Category
from common.validators import validate_image_upload

from .models import Business, BusinessCategory

DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@extend_schema_field(OpenApiTypes.BINARY)
class BinaryImageField(serializers.ImageField):
    """Document uploaded image files as binary payloads for Swagger."""


BUSINESS_HOURS_SCHEMA = {
    "type": "object",
    "properties": {
        day: {
            "type": "object",
            "properties": {
                "is_open": {"type": "boolean"},
                "open": {"type": "string", "format": "time"},
                "close": {"type": "string", "format": "time"},
            },
            "required": ["is_open", "open", "close"],
            "additionalProperties": False,
        }
        for day in DAYS
    },
    "required": list(DAYS),
    "additionalProperties": False,
}


@extend_schema_field(BUSINESS_HOURS_SCHEMA)
class BusinessHoursField(serializers.JSONField):
    """Document the nested weekly opening-hours object for Swagger."""


class BusinessSerializer(serializers.ModelSerializer):
    """Validates and serializes vendor business information."""

    description = serializers.CharField(max_length=500)
    business_hours = BusinessHoursField(required=False, default=dict)
    logo = BinaryImageField(
        required=False,
        allow_null=True,
        validators=[validate_image_upload],
    )
    cover_image = BinaryImageField(
        required=False,
        allow_null=True,
        validators=[validate_image_upload],
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Business
        fields = (
            "id",
            "name",
            "description",
            "contact",
            "email",
            "address",
            "city_district",
            "business_hours",
            "logo",
            "cover_image",
            "category",
            "verification_status",
        )
        read_only_fields = (
            "id",
            "verification_status",
        )


    @transaction.atomic
    def create(self, validated_data):
        category = validated_data.pop("category", None)
        business = super().create(validated_data)

        if category:
            BusinessCategory.objects.create(
                business=business,
                category=category,
            )

        return business

    def update(self, instance, validated_data):
        # The category is chosen at registration; changing it later
        # goes through the category approval flow.
        validated_data.pop("category", None)
        return super().update(instance, validated_data)

    def validate_name(self, value):
        request = self.context.get("request")

        if request is None:
            return value

        duplicates = Business.objects.filter(
            vendor=request.user,
            name__iexact=value,
        )

        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)

        if duplicates.exists():
            raise serializers.ValidationError(
                "You already have a business with this name."
            )

        return value

    def validate_contact(self, value):
        number = re.sub(r"[\s-]", "", value)

        if not re.fullmatch(r"\+256\d{9}", number):
            raise serializers.ValidationError(
                "Enter a valid Ugandan phone number, "
                "e.g. +256700123456."
            )

        return number

    def validate_business_hours(self, value):
        if not isinstance(value, dict) or set(value) != set(DAYS):
            raise serializers.ValidationError(
                "Provide hours for all seven days."
            )

        for day, entry in value.items():
            if not isinstance(entry, dict):
                raise serializers.ValidationError(
                    f"Invalid hours for {day}."
                )

            is_open = entry.get("is_open")

            if not isinstance(is_open, bool):
                raise serializers.ValidationError(
                    f"{day.title()} must specify whether "
                    "the business is open."
                )

            if not is_open:
                continue

            try:
                opens = time.fromisoformat(entry["open"])
                closes = time.fromisoformat(entry["close"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError(
                    f"{day.title()} needs valid opening "
                    "and closing times."
                )

            if opens >= closes:
                raise serializers.ValidationError(
                    f"{day.title()} must open before it closes."
                )

        return value


class BusinessWriteSerializer(BusinessSerializer):
    """Serializer used for create/update request bodies in Swagger and DRF."""

    class Meta(BusinessSerializer.Meta):
        fields = (
            "name",
            "description",
            "contact",
            "email",
            "address",
            "city_district",
            "business_hours",
            "logo",
            "cover_image",
            "category",
        )
        read_only_fields = ()