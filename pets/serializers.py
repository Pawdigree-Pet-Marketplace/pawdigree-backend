from rest_framework import serializers

from businesses.models import Business

from .models import Pet


class PetSerializer(serializers.ModelSerializer):
    """Serialize pet listings and enforce business ownership."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.all(),
    )

    class Meta:
        model = Pet
        fields = (
            "pet_id",
            "vendor",
            "business",
            "listing_type",
            "name",
            "species",
            "breed",
            "age",
            "gender",
            "size",
            "description",
            "approved",
            "price",
            "adoption_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "pet_id",
            "vendor",
            "approved",
            "created_at",
            "updated_at",
        )

    def validate_business(self, value):
        request = self.context.get("request")

        if request is None or value.vendor_id != request.user.pk:
            raise serializers.ValidationError(
                "You can only list pets under your own business."
            )

        return value
