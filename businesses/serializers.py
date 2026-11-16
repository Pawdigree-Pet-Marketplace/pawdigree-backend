from datetime import time

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from categories.models import Category
from common.phone import normalize_phone_number
from common.validators import validate_image_upload
from documents.serializers import BusinessDocumentReadSerializer

from .models import Business, BusinessCategory, BusinessDecision, BusinessImage

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
    business_type = serializers.ChoiceField(
        choices=Business.BusinessType.choices,
        required=True,
    )
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
             "business_type",
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
        return normalize_phone_number(value)

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


class PublicBusinessSerializer(serializers.ModelSerializer):
    """Public information for approved businesses."""

    categories = serializers.SerializerMethodField()

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
            "categories",
        )
        read_only_fields = fields

    def get_categories(self, obj) -> list[str]:
        return [
            business_category.category.name
            for business_category in obj.business_categories.all()
        ]


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
            "business_type",
            "business_hours",
            "logo",
            "cover_image",
            "category",
        )
        read_only_fields = ()


class VendorResponseSerializer(serializers.ModelSerializer):
    """Validates a vendor's response to requested business changes."""

    vendor_response = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=5000,
    )

    class Meta:
        model = Business
        fields = ("vendor_response",)


def can_sell_in_category(business_category):
    """A vendor may sell under a category once both it and the business are approved."""
    business = business_category.business

    return (
        business.is_active
        and business.verification_status == Business.VerificationStatus.APPROVED
        and business_category.approval_status
        == BusinessCategory.ApprovalStatus.APPROVED
    )


class BusinessCategoryStatusSerializer(serializers.ModelSerializer):
    """A category the business asked to sell under, and its approval."""

    category_id = serializers.IntegerField(source="category.id", read_only=True)
    name = serializers.CharField(source="category.name", read_only=True)
    can_sell = serializers.SerializerMethodField()

    class Meta:
        model = BusinessCategory
        fields = ("category_id", "name", "approval_status", "can_sell")
        read_only_fields = fields

    def get_can_sell(self, obj) -> bool:
        return can_sell_in_category(obj)


class BusinessVerificationStatusSerializer(serializers.ModelSerializer):
    """A vendor's view of one business's verification and selling status."""

    categories = BusinessCategoryStatusSerializer(
        source="business_categories",
        many=True,
        read_only=True,
    )
    can_sell = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = (
            "id",
            "name",
            "verification_status",
            "decision_reason",
            "reviewed_at",
            "is_active",
            "can_sell",
            "categories",
        )
        read_only_fields = fields

    def get_can_sell(self, obj) -> bool:
        return any(
            can_sell_in_category(business_category)
            for business_category in obj.business_categories.all()
        )


class CategoryRequestSerializer(serializers.Serializer):
    """Validates the categories a vendor wants to offer through a business."""

    category_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(
            queryset=Category.objects.filter(is_active=True)
        ),
        allow_empty=False,
    )

    def validate_category_ids(self, categories):
        business = self.context.get("business")
        expected_kind_by_business_type = {
            Business.BusinessType.PET_SALE_ADOPTION: Category.Kind.PETS,
            Business.BusinessType.PRODUCT_SELLER: Category.Kind.MERCHANDISE,
            Business.BusinessType.SERVICE_PROVIDER: Category.Kind.SERVICES,
        }
        expected_kind = expected_kind_by_business_type.get(
            getattr(business, "business_type", None)
        )
        if expected_kind is None:
            raise serializers.ValidationError(
                "Set a supported business type before requesting categories."
            )
        if any(category.kind != expected_kind for category in categories):
            raise serializers.ValidationError(
                f"Choose only active {expected_kind} categories for this business."
            )

        # Keep each category only once, even if an ID is repeated.
        unique_categories = {}
        for category in categories:
            unique_categories[category.pk] = category

        return list(unique_categories.values())
    
    
Action = BusinessDecision.Action
Status = Business.VerificationStatus

DECISION_RULES = {
    Action.APPROVE.value: {
        "from": (Status.PENDING.value,),
        "to": Status.APPROVED.value,
        "reason_required": False,
    },
    Action.REQUEST_CHANGES.value: {
        "from": (Status.PENDING.value, Status.APPROVED.value),
        "to": Status.CHANGES_REQUESTED.value,
        "reason_required": True,
    },
    Action.SUSPEND.value: {
        "from": (Status.APPROVED.value,),
        "to": Status.SUSPENDED.value,
        "reason_required": True,
    },
    Action.REAPPROVE.value: {
        "from": (Status.SUSPENDED.value,),
        "to": Status.APPROVED.value,
        "reason_required": False,
    },
}



class BusinessImageReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessImage
        fields = ("id", "image", "alt_text", "display_order")
        read_only_fields = fields


class AdminBusinessReviewSerializer(serializers.ModelSerializer):
    """Everything an admin needs to review one vendor application."""

    vendor_email = serializers.EmailField(source="vendor.email", read_only=True)
    vendor_username = serializers.CharField(
        source="vendor.username", read_only=True
    )
    images = BusinessImageReadSerializer(many=True, read_only=True)
    documents = BusinessDocumentReadSerializer(many=True, read_only=True)
    categories = BusinessCategoryStatusSerializer(
        source="business_categories", many=True, read_only=True
    )

    class Meta:
        model = Business
        fields = (
            "id",
            "vendor_email",
            "vendor_username",
            "name",
            "description",
            "contact",
            "email",
            "address",
            "city_district",
            "business_hours",
            "logo",
            "cover_image",
            "images",
            "documents",
            "categories",
            "verification_status",
            "decision_reason",
            "vendor_response",
            "reviewed_at",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields



class BusinessDecisionInputSerializer(serializers.Serializer):
    """Validates an admin decision. Needs context={"business": business}."""

    action = serializers.ChoiceField(choices=BusinessDecision.Action.choices)
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=5000,
    )

    def validate(self, attrs):
        business = self.context["business"]
        rule = DECISION_RULES[attrs["action"]]
        current = business.verification_status

        if current not in rule["from"]:
            raise serializers.ValidationError({
                "action": (
                    "You can't do this to a business that is "
                    f"{current.replace('_', ' ')}."
                )
            })

        if rule["reason_required"] and not attrs.get("reason"):
            raise serializers.ValidationError({
                "reason": "A reason is required for this decision."
            })

        attrs["from_status"] = current
        attrs["to_status"] = rule["to"]
        return attrs


class BusinessDecisionHistorySerializer(serializers.ModelSerializer):
    decided_by_email = serializers.EmailField(
        source="decided_by.email", read_only=True, allow_null=True
    )

    class Meta:
        model = BusinessDecision
        fields = (
            "id",
            "action",
            "from_status",
            "to_status",
            "reason",
            "decided_by_email",
            "created_at",
        )
        read_only_fields = fields
