from rest_framework import serializers

from .models import Payment


class StartPaymentSerializer(serializers.Serializer):
    """Check what the customer sends to start a payment."""

    order_id = serializers.IntegerField(min_value=1)
    method = serializers.CharField(max_length=30)


class PaymentSerializer(serializers.ModelSerializer):
    """What the frontend sees about a payment."""

    order_status = serializers.CharField(source="order.status", read_only=True)
    order_expires_at = serializers.DateTimeField(source="order.expires_at", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order",
            "order_status",
            "order_expires_at",
            "method",
            "amount",
            "currency",
            "status",
            "payment_url",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields