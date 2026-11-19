from decimal import Decimal

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
    pet_id = serializers.IntegerField(read_only=True)
    item_type = serializers.CharField(read_only=True)
    name = serializers.CharField(source="item_name", read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrderItem
        fields = (
            "id", "item_type", "product_id", "pet_id", "name",
            "quantity", "unit_price", "subtotal",
        )
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


class VendorOrderDetailSerializer(serializers.ModelSerializer):
    """One vendor order, with what the vendor needs to pack and ship it."""

    order_id = serializers.ReadOnlyField()
    business_name = serializers.CharField(source="business.name", read_only=True)
    shipping_name = serializers.CharField(source="order.shipping_name", read_only=True)
    shipping_phone = serializers.CharField(source="order.shipping_phone", read_only=True)
    shipping_address = serializers.CharField(
        source="order.shipping_address", read_only=True
    )
    shipping_city_district = serializers.CharField(
        source="order.shipping_city_district", read_only=True
    )
    notes = serializers.CharField(source="order.notes", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = VendorOrder
        fields = (
            "id",
            "order_id",
            "business_name",
            "status",
            "shipping_name",
            "shipping_phone",
            "shipping_address",
            "shipping_city_district",
            "notes",
            "items",
            "total",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_total(self, obj) -> str:
        total = sum((item.subtotal for item in obj.items.all()), Decimal("0.00"))
        return str(total.quantize(Decimal("0.01")))


class VendorOrderStatusSerializer(serializers.Serializer):
    """The new status a vendor wants to give an order."""

    status = serializers.ChoiceField(choices=VendorOrder.Status.choices)
