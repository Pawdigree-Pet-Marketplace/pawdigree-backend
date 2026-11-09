from rest_framework import serializers

from common.phone import normalize_phone_number

from .models import Order, OrderItem, VendorOrder


class CheckoutSerializer(serializers.Serializer):
    """Validates the shipping and contact details sent at checkout."""

    shipping_name = serializers.CharField(max_length=150)
    shipping_phone = serializers.CharField(max_length=20)
    shipping_address = serializers.CharField(max_length=255)
    shipping_city_district = serializers.CharField(max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_shipping_phone(self, value):
        # Stored as E.164, like every other phone number in Pawdigree.
        return normalize_phone_number(value)


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrderItem
        fields = ("id", "product_id", "name", "quantity", "unit_price", "subtotal")
        read_only_fields = fields


class VendorOrderSerializer(serializers.ModelSerializer):
    business_id = serializers.IntegerField(read_only=True)
    business_name = serializers.CharField(source="business.name", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = VendorOrder
        fields = ("id", "business_id", "business_name", "status", "items")
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    vendor_orders = VendorOrderSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "items_subtotal",
            "total_amount",
            "expires_at",
            "shipping_name",
            "shipping_phone",
            "shipping_address",
            "shipping_city_district",
            "notes",
            "created_at",
            "vendor_orders",
        )
        read_only_fields = fields
