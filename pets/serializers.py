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

    def validate(self, attrs):
        listing_type = attrs.get(
            "listing_type",
            self.instance.listing_type
            if self.instance
            else Pet.ListingType.ADOPTION,
        )
        price = attrs.get(
            "price",
            self.instance.price if self.instance else None,
        )

        if listing_type == Pet.ListingType.SALE:
            if price is None or price <= 0:
                raise serializers.ValidationError({
                    "price": (
                        "A sale listing must have a price greater than zero."
                    )
                })
        elif listing_type == Pet.ListingType.ADOPTION and price is not None:
            raise serializers.ValidationError({
                "price": "An adoption listing must not have a price."
            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        pet = Pet.objects.create(**validated_data)

        for image_data in images_data:
            PetImage.objects.create(pet=pet, **image_data)

        return pet
