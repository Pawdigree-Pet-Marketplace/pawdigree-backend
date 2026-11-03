from rest_framework import serializers

from businesses.models import Business
from categories.models import Category

from .models import Product, ProductImage


class ProductImageSerializer(serializers.ModelSerializer):
    """Serialize images associated with a product."""

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "image",
            "alt_text",
            "display_order",
        )
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    """Validate and serialize merchandise managed by administrators."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.all(),
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
    )
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "business",
            "category",
            "name",
            "description",
            "price",
            "stock_quantity",
            "is_active",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "images",
            "created_at",
            "updated_at",
        )

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "The product price must be greater than zero."
            )

        return value
