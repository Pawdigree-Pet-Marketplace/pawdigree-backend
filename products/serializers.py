from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from businesses.models import Business
from categories.models import Category
from common.validators import validate_description_length
from .performance import LOW_STOCK_THRESHOLD
from reviews.services import rating_summary
from reviews.serializers import RatingSummaryMixin

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
        queryset=Category.objects.filter(
            is_active=True,
            kind=Category.Kind.MERCHANDISE,
        ),
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
            "approved",
            "rejection_reason",
            "reviewed_at",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "approved",
            "rejection_reason",
            "reviewed_at",
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

    def validate_description(self, value):
        validate_description_length(value)
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

    # Changing any of these sends the product back to admin review.
    REVIEWED_FIELDS = ("name", "description", "category")

    def update(self, instance, validated_data):
        changed = any(
            field in validated_data
            and validated_data[field] != getattr(instance, field)
            for field in self.REVIEWED_FIELDS
        )
        if changed:
            instance.send_back_for_review(save=False)

        return super().update(instance, validated_data)


class ProductRejectSerializer(serializers.Serializer):
    """The reason an administrator gives when rejecting a product."""

    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class ProductImageUploadSerializer(serializers.ModelSerializer):
    """Accept an uploaded image for a product."""

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "image",
            "alt_text",
            "display_order",
        )
        read_only_fields = ("id",)


class PublicProductSerializer(serializers.ModelSerializer):
    """What a customer sees on the merchandise page."""

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    business_name = serializers.CharField(
        source="business.name",
        read_only=True,
    )
    is_available = serializers.BooleanField(read_only=True)
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "price",
            "category",
            "category_name",
            "business_name",
            "is_available",
            "main_image",
        )

    @extend_schema_field({"type": "string", "format": "uri", "nullable": True})
    def get_main_image(self, obj):
        first = next(iter(obj.images.all()), None)
        if first is None:
            return None

        request = self.context.get("request")
        url = first.image.url
        return request.build_absolute_uri(url) if request else url


class PublicProductDetailSerializer(RatingSummaryMixin, PublicProductSerializer):
    """The full product page: the list fields plus description and images."""

    images = ProductImageSerializer(many=True, read_only=True)
    rating_field = "product"
    class Meta(PublicProductSerializer.Meta):
        fields = PublicProductSerializer.Meta.fields + (
            "description",
            "images",
            "average_rating",
            "review_count",
        )          

class PerformanceQuerySerializer(serializers.Serializer):
    """Validates the query string of the admin performance endpoints."""

    SORT_CHOICES = ("top_selling", "revenue", "lowest_stock", "name")

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    low_stock_threshold = serializers.IntegerField(
        required=False, min_value=0, default=LOW_STOCK_THRESHOLD
    )
    business = serializers.IntegerField(required=False, min_value=1)
    low_stock = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)
    sort = serializers.ChoiceField(choices=SORT_CHOICES, default="top_selling")

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_from": "date_from cannot be after date_to."}
            )
        return attrs


class BusinessPerformanceSerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True)
    low_stock_count = serializers.IntegerField(read_only=True)
    orders_count = serializers.IntegerField(read_only=True)
    units_sold = serializers.IntegerField(read_only=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Business
        fields = (
            "id", "name", "products_count", "low_stock_count",
            "orders_count", "units_sold", "revenue",
        )
        read_only_fields = fields


class ProductPerformanceSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source="business.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    units_sold = serializers.IntegerField(read_only=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "business", "business_name", "category_name", "name",
            "price", "stock_quantity", "is_active", "approved",
            "units_sold", "revenue", "is_low_stock",
        )
        read_only_fields = fields
        
        

