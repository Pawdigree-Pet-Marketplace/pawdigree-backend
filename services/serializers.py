from django.db import transaction
from rest_framework import serializers

from businesses.models import Business, BusinessCategory
from categories.models import Category

from .models import Service

# Same rule as the category request endpoint: a business in one of these
# states can't ask for new categories.
BLOCKED_STATUSES = (
    Business.VerificationStatus.SUSPENDED,
    Business.VerificationStatus.REJECTED,
)


class ServiceSerializer(serializers.ModelSerializer):
    """Validates and serializes service details."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.none(),
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
    )
    category_status = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "service_id",
            "business",
            "category",
            "category_status",
            "name",
            "service_type",
            "description",
            "price",
            "duration",
            "availability_status",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "service_id",
            "is_active",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["business"].queryset = Business.objects.filter(
                vendor=request.user,
            )

    def get_category_status(self, obj) -> str | None:
        """Approval status of this category for the service's business."""
        if obj.category_id is None:
            return None

        link = BusinessCategory.objects.filter(
            business=obj.business,
            category_id=obj.category_id,
        ).first()

        return link.approval_status if link else None

    def validate_duration(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Duration must be greater than zero."
            )
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Price must not be negative."
            )
        return value

    def validate(self, attrs):
        category = attrs.get("category")
        if category is None:
            return attrs

        # On edit the business is read-only, so take it from the service.
        business = attrs.get("business") or self.instance.business
        link = BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).first()

        if link is None:
            if (
                not business.is_active
                or business.verification_status in BLOCKED_STATUSES
            ):
                raise serializers.ValidationError({
                    "category": (
                        "This business can't request new categories "
                        "right now."
                    )
                })
        elif link.approval_status == BusinessCategory.ApprovalStatus.REJECTED:
            raise serializers.ValidationError({
                "category": (
                    "This category was rejected for your business. "
                    "Re-apply for it from your business page first."
                )
            })

        return attrs

    @staticmethod
    def _request_category(business, category):
        """Make sure the business has asked for this category.

        A new request starts as pending. The business keeps its current
        verification status, and the service stays unavailable to
        customers until the category is approved.
        """
        if category is not None:
            BusinessCategory.objects.get_or_create(
                business=business,
                category=category,
            )

    @transaction.atomic
    def create(self, validated_data):
        self._request_category(
            validated_data["business"],
            validated_data.get("category"),
        )
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        self._request_category(
            instance.business,
            validated_data.get("category"),
        )
        return super().update(instance, validated_data)


class ServiceUpdateSerializer(ServiceSerializer):
    """Edit a service. The business it belongs to cannot be changed."""

    business = serializers.PrimaryKeyRelatedField(read_only=True)
    # Optional on edit, so older services and small edits keep working.
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
    )