from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Payment
from .refunds import received_amount


def _name(user):
    return user.get_full_name().strip() or user.username


class MarkRefundedSerializer(serializers.Serializer):
    """What an administrator sends to record a refund they have paid."""

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    gateway_reference = serializers.CharField(max_length=100)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AdminRefundPaymentSerializer(serializers.ModelSerializer):
    """A payment as an administrator reviews it for a refund."""

    order_id = serializers.IntegerField(read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    customer = serializers.SerializerMethodField()
    received_amount = serializers.SerializerMethodField()
    refund = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "order_id",
            "order_status",
            "customer",
            "method",
            "amount",
            "currency",
            "received_amount",
            "status",
            "gateway_reference",
            "gateway_transaction_id",
            "failure_reason",
            "paid_at",
            "created_at",
            "refund",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_customer(self, obj):
        customer = obj.order.customer
        return {"id": customer.pk, "name": _name(customer), "email": customer.email}

    @extend_schema_field(OpenApiTypes.STR)
    def get_received_amount(self, obj):
        received = received_amount(obj)
        return str(received) if received is not None else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_refund(self, obj):
        refund = getattr(obj, "refund", None)
        if refund is None:
            return None
        return {
            "amount": str(refund.amount),
            "currency": refund.currency,
            "reason": refund.reason,
            "gateway_reference": refund.gateway_reference,
            "refunded_by": {
                "id": refund.refunded_by_id,
                "name": _name(refund.refunded_by),
            },
            "refunded_at": refund.created_at,
        }
