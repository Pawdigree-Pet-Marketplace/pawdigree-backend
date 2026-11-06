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


class VendorProductSerializer(ProductSerializer):
    """Serialize products while restricting vendors to their own businesses."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.none(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["business"].queryset = Business.objects.filter(
                vendor=request.user,
            )

    def validate_business(self, business):
        # An existing product can stay with its current business even if
        # that business is later suspended.
        if self.instance is not None and self.instance.business_id == business.pk:
            return business

        if (
            not business.is_active
            or business.verification_status
            != Business.VerificationStatus.APPROVED
        ):
            raise serializers.ValidationError(
                "Your business must be approved before you can add products."
            )

        if business.business_type != Business.BusinessType.PRODUCT_SELLER:
            raise serializers.ValidationError(
                "Only Pet Merchandise businesses can add products."
            )

        return business
    
