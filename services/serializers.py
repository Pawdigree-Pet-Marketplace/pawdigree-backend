
from datetime import date, datetime

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from businesses.models import Business
from categories.models import Category
from common.validators import validate_description_length
from reviews.serializers import RatingSummaryMixin

from .models import AvailabilitySlot, Service


class ServiceSerializer(serializers.ModelSerializer):
    """Validates and serializes service details."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.none(),
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(
            is_active=True,
            kind=Category.Kind.SERVICES,
        ),
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
            "image",
            "price",
            "duration",
            "availability_status",
            "is_active",
            "approved",
            "rejection_reason",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "service_id",
            "is_active",
            "approved",
            "rejection_reason",
            "reviewed_at",
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
        """Return the admin catalogue status of the service category."""
        if obj.category_id is None:
            return None

        if (
            obj.category.is_active
            and obj.category.kind == Category.Kind.SERVICES
        ):
            return "approved"

        return None

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

    def validate_business(self, business):
        if (
            not business.is_active
            or business.verification_status
            != Business.VerificationStatus.APPROVED
        ):
            raise serializers.ValidationError(
                "Your business must be approved before you can add services."
            )

        if business.business_type != Business.BusinessType.SERVICE_PROVIDER:
            raise serializers.ValidationError(
                "Only Pet Services businesses can add services."
            )

        return business

    @transaction.atomic
    def create(self, validated_data):
        return super().create(validated_data)

    def validate_description(self, value):
        validate_description_length(value)
        return value

    # Changing any of these sends the service back to admin review.
    REVIEWED_FIELDS = ("name", "service_type", "description", "category")

    def _changes_reviewed_content(self, instance, validated_data):
        for field in self.REVIEWED_FIELDS:
            if (
                field in validated_data
                and validated_data[field] != getattr(instance, field)
            ):
                return True

        if "image" in validated_data:
            # Adding or replacing an image, or removing an existing one.
            return bool(validated_data["image"]) or bool(instance.image)

        return False

    @transaction.atomic
    def update(self, instance, validated_data):
        if self._changes_reviewed_content(instance, validated_data):
            instance.send_back_for_review(save=False)

        return super().update(instance, validated_data)


class ServiceUpdateSerializer(ServiceSerializer):
    """Edit a service. The business it belongs to cannot be changed."""

    business = serializers.PrimaryKeyRelatedField(read_only=True)


class ServiceRejectSerializer(serializers.Serializer):
    """The reason an administrator gives when rejecting a service."""

    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class PublicServiceSerializer(RatingSummaryMixin, serializers.ModelSerializer):
    """Customer-facing service card with a business-logo image fallback."""
    rating_field = "service"
    category_name = serializers.CharField(source="category.name", read_only=True)
    business_name = serializers.CharField(source="business.name", read_only=True)
    city_district = serializers.CharField(
        source="business.city_district",
        read_only=True,
    )
    image = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "service_id",
            "name",
            "service_type",
            "description",
            "price",
            "duration",
            "availability_status",
            "category_name",
            "business_name",
            "city_district",
            "image",
            "average_rating",
            "review_count",
        )
        read_only_fields = fields

    @extend_schema_field({"type": "string", "format": "uri", "nullable": True})
    def get_image(self, obj):
        image = obj.image or obj.business.logo
        if not image:
            return None

        url = image.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    """Validates one weekly time slot. Needs context={"service": service}."""

    class Meta:
        model = AvailabilitySlot
        fields = (
            "slot_id",
            "weekday",
            "start_time",
            "end_time",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("slot_id", "created_at", "updated_at")

    def validate(self, attrs):
        # The service comes from the URL, so the view passes it in context.
        service = self.context["service"]
        weekday = attrs["weekday"]
        start = attrs["start_time"]
        end = attrs["end_time"]

        # The slot must run forward in time.
        if end <= start:
            raise serializers.ValidationError({
                "end_time": "End time must be after start time."
            })

        # The slot must be long enough for at least one booking.
        length = datetime.combine(date.min, end) - datetime.combine(date.min, start)
        minutes = int(length.total_seconds() // 60)
        if minutes < service.duration:
            raise serializers.ValidationError({
                "end_time": (
                    f"This slot is {minutes} minutes long, but the service "
                    f"takes {service.duration} minutes."
                )
            })

        # Two slots overlap when each one starts before the other ends.
        # Using strict < and > means back-to-back slots are allowed.
        clash = AvailabilitySlot.objects.filter(
            service=service,
            weekday=weekday,
            start_time__lt=end,
            end_time__gt=start,
        ).first()
        if clash:
            raise serializers.ValidationError({
                "start_time": (
                    "This overlaps an existing slot "
                    f"({clash.start_time:%H:%M} to {clash.end_time:%H:%M}) "
                    "on that day."
                )
            })

        return attrs


class CalendarDaySerializer(serializers.Serializer):
    """One day of the weekly calendar and its slots."""

    weekday = serializers.IntegerField()
    day = serializers.CharField()
    slots = AvailabilitySlotSerializer(many=True)


class ServiceCalendarSerializer(serializers.Serializer):
    """A service's weekly availability, grouped by day."""

    service_id = serializers.IntegerField()
    service_name = serializers.CharField()
    duration = serializers.IntegerField()
    availability_status = serializers.CharField()
    days = CalendarDaySerializer(many=True)
