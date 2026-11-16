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