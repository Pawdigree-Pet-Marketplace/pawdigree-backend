import re
from datetime import time

from rest_framework import serializers

from .models import Business

DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


class BusinessSerializer(serializers.ModelSerializer):
    """Validates and serializes vendor business information."""

    description = serializers.CharField(max_length=500)

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
            "verification_status",
        )
        read_only_fields = (
            "id",
            "verification_status",
        )

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