from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from bookings.models import Booking
from orders.models import Order
from orders.serializers import OrderItemSerializer, VendorOrderDetailSerializer


def _customer_name(user):
    """Full name, else username. Anything that looks like an email address is
    never shown to a vendor."""
    name = user.get_full_name().strip() or user.username
    return "Customer" if "@" in name else name


class OrderTransactionSerializer(VendorOrderDetailSerializer):
    """A paid merchandise order, as the vendor sees it."""

    business_id = serializers.UUIDField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()

    class Meta(VendorOrderDetailSerializer.Meta):
        fields = VendorOrderDetailSerializer.Meta.fields + (
            "business_id",
            "status_display",
            "customer",
            "payment",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_customer(self, obj):
        customer = obj.order.customer
        return {"id": customer.pk, "name": _customer_name(customer)}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_payment(self, obj):
        """Only what a vendor may see. The payment amount covers the whole
        checkout and the gateway details are internal, so neither is shown."""
        if obj.order.status != Order.Status.PAID:
            return None
        payment = getattr(obj.order, "payment", None)
        if payment is None:
            return None
        return {
            "method": payment.method,
            "status": payment.status,
            "reference": payment.gateway_reference,
            "paid_at": payment.paid_at,
        }


class PetSaleItemSerializer(OrderItemSerializer):
    pet = serializers.SerializerMethodField()

    class Meta(OrderItemSerializer.Meta):
        fields = OrderItemSerializer.Meta.fields + ("pet",)
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_pet(self, obj):
        pet = obj.pet
        if pet is None:
            return None
        return {
            "pet_id": pet.pk,
            "name": pet.name,
            "species": pet.species,
            "breed": pet.breed,
            "gender": pet.gender,
            "age": pet.age,
            "size": pet.size,
            "adoption_status": pet.adoption_status,
        }


class PetSaleTransactionSerializer(OrderTransactionSerializer):
    """A paid pet sale, or a pet that is being held for an unpaid checkout.

    sale_state tells the two apart: PAID, or RESERVED while the customer still
    has to pay. A reservation lasts until reservation_expires_at.
    """

    items = PetSaleItemSerializer(many=True, read_only=True)
    sale_state = serializers.SerializerMethodField()
    reservation_expires_at = serializers.SerializerMethodField()

    class Meta(OrderTransactionSerializer.Meta):
        fields = OrderTransactionSerializer.Meta.fields + (
            "sale_state",
            "reservation_expires_at",
        )
        read_only_fields = fields

    def _is_reserved(self, obj):
        return obj.order.status == Order.Status.PENDING_PAYMENT

    def get_sale_state(self, obj) -> str:
        return "RESERVED" if self._is_reserved(obj) else "PAID"

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_reservation_expires_at(self, obj):
        return obj.order.expires_at if self._is_reserved(obj) else None


class BookingTransactionSerializer(serializers.ModelSerializer):
    business_id = serializers.UUIDField(source="service.business_id", read_only=True)
    business_name = serializers.CharField(source="service.business.name", read_only=True)
    service_id = serializers.IntegerField(read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            "booking_id",
            "business_id",
            "business_name",
            "service_id",
            "service_name",
            "customer",
            "start_at",
            "end_at",
            "status",
            "status_display",
            "notes",
            "decision_reason",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_customer(self, obj):
        customer = obj.customer
        return {
            "id": customer.pk,
            "name": _customer_name(customer),
            "phone": customer.phone,
        }
