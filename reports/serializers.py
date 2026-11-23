from collections.abc import Mapping

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from common.validators import validate_description_length
from pets.models import Pet
from products.models import Product
from reviews.models import Review
from services.models import Service

from .models import Report


TARGET_MODELS = {
    Report.ReportedItemType.PET: Pet,
    Report.ReportedItemType.PRODUCT: Product,
    Report.ReportedItemType.SERVICE: Service,
    Report.ReportedItemType.REVIEW: Review,
}


class ReportSubmissionSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=Report.Reason.choices)
    description = serializers.CharField(
        validators=[validate_description_length],
    )
    reported_item_type = serializers.ChoiceField(
        choices=Report.ReportedItemType.choices,
    )
    reported_item_id = serializers.CharField(
        required=False,
        allow_null=True,
        trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = set(data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError(
                    {
                        field: "This field is not allowed."
                        for field in sorted(unknown_fields)
                    }
                )

        return super().to_internal_value(data)

    def validate(self, attrs):
        target_type = attrs["reported_item_type"]
        item_id = attrs.get("reported_item_id")

        if target_type == Report.ReportedItemType.GENERAL:
            if item_id is not None:
                raise serializers.ValidationError(
                    {"reported_item_id": "General reports cannot include an item ID."}
                )
            return attrs

        if item_id is None:
            raise serializers.ValidationError(
                {"reported_item_id": "This field is required for this target type."}
            )

        model = TARGET_MODELS[target_type]
        try:
            primary_key_field = model._meta.pk
            converted_id = primary_key_field.to_python(item_id)
            primary_key_field.run_validators(converted_id)
        except (DjangoValidationError, TypeError, ValueError, OverflowError):
            raise serializers.ValidationError(
                {"reported_item_id": "Enter a valid ID for this target type."}
            )

        if not model._base_manager.filter(pk=converted_id).exists():
            raise serializers.ValidationError(
                {"reported_item_id": "The specified target does not exist."}
            )

        attrs["reported_item_id"] = str(converted_id)
        return attrs


class ReportResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = (
            "id",
            "reason",
            "description",
            "reported_item_type",
            "reported_item_id",
            "status",
            "created_at",
        )
        read_only_fields = fields
