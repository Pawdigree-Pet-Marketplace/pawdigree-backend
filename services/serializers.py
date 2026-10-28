from rest_framework import serializers

from businesses.models import Business

from .models import Service


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
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "service_id",
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
