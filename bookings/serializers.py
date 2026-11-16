from datetime import datetime

from rest_framework import serializers

from services.views import public_services

from .availability import booking_tz
from .models import Booking


class FreeTimesQuerySerializer(serializers.Serializer):
    date = serializers.DateField()

    def validate_date(self, value):
        today = datetime.now(booking_tz()).date()
        if value < today:
            raise serializers.ValidationError("Date can't be in the past.")
        return value


class FreeTimesSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()
    date = serializers.DateField()
    duration = serializers.IntegerField()
    times = serializers.ListField(child=serializers.CharField())

class BookingCreateSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(queryset=public_services())
    start_at = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)


class BookingSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = Booking
        fields = (
            "booking_id",
            "service",
            "service_name",
            "start_at",
            "end_at",
            "status",
            "notes",
            "created_at",
        )
        read_only_fields = fields


class VendorBookingSerializer(serializers.ModelSerializer):
    """Booking details vendors need to identify and manage their customers."""

    customer_id = serializers.IntegerField(source="customer.pk", read_only=True)
    customer_name = serializers.SerializerMethodField()
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = Booking
        fields = (
            "booking_id",
            "customer_id",
            "customer_name",
            "service_name",
            "start_at",
            "end_at",
            "status",
            "notes",
            "decision_reason",
            "created_at",
        )
        read_only_fields = fields

    def get_customer_name(self, obj) -> str:
        full_name = obj.customer.get_full_name().strip()
        return full_name or obj.customer.username


class VendorBookingStatusSerializer(serializers.Serializer):
    """Validate a vendor's requested booking status transition."""

    status = serializers.ChoiceField(
        choices=(
            (Booking.Status.ACCEPTED, "Accepted"),
            (Booking.Status.DECLINED, "Declined"),
            (Booking.Status.COMPLETED, "Completed"),
        )
    )
    decision_reason = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True
    )

    def validate(self, attrs):
        if (
            attrs["status"] == Booking.Status.DECLINED
            and not attrs.get("decision_reason", "").strip()
        ):
            raise serializers.ValidationError(
                {"decision_reason": "A reason is required when declining a booking."}
            )
        return attrs


class BookingRescheduleSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()

