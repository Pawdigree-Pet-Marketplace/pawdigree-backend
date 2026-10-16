from django.db import transaction
from rest_framework import serializers

from businesses.models import Business

from .models import Pet, PetImage


class PetImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetImage
        fields = (
            "image_id",
            "image",
            "is_primary",
            "position",
            "created_at",
        )
        read_only_fields = ("image_id", "created_at")


class PetSerializer(serializers.ModelSerializer):
    """Serialize pet listings and persist their uploaded images."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.all(),
    )
    images = PetImageSerializer(many=True, required=False)

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
            "images",
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

    @transaction.atomic
    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        pet = Pet.objects.create(**validated_data)

        for image_data in images_data:
            PetImage.objects.create(pet=pet, **image_data)

        return pet
