from rest_framework import serializers

from businesses.models import Business
from datetime import date, datetime

from .models import Service, AvailabilitySlot


class ServiceSerializer(serializers.ModelSerializer):
    """Validates and serializes service details."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.none(),
    )

    class Meta:
        model = Service
        fields = (
            "service_id",
            "business",
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

class ServiceUpdateSerializer(ServiceSerializer):
    """Edit a service. The business it belongs to cannot be changed."""

    business = serializers.PrimaryKeyRelatedField(read_only=True)
    
    
class AvailabilitySlotSerializer(serializers.ModelSerializer):
    """validates on weekly time slot. needs context={"service": service}."""
    
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
        
        #the slot must run forward in time.
        if end <= start:
            raise serializers.ValidationError({
                "end_time": "End time must be after start time."
            })
            
        #the slot must be long enough for atleast one booking.
        length = datetime.combine(date.min, end) - datetime.combine(date.min, start)
        minutes = int(length.total_seconds() // 60)
        if minutes < service.duration:
            raise serializers.ValidationError({
                "end_time": (
                    f"This slot is {minutes} minutes long, but the service "
                    f"takes {service.duration} minutes."
                )
            })
        #Two slots overlap when each one starts before the other ends.
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