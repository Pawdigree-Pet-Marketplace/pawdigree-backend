"""Vendor transaction lists: merchandise orders, pet sales and bookings.

These only read. Checkout, payment and status changes are untouched; vendors
keep changing statuses through the existing PATCH endpoints.
"""

import uuid

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError

from bookings.models import Booking
from businesses.models import Business
from common.pagination import VendorTransactionPagination
from common.permissions import IsVendor
from orders.models import Order, OrderItem, VendorOrder
from pets.models import Pet

from .serializers import (
    BookingTransactionSerializer,
    OrderTransactionSerializer,
    PetSaleTransactionSerializer,
)

ORDER_STATUSES = [
    VendorOrder.Status.PAID.value,
    VendorOrder.Status.PROCESSING.value,
    VendorOrder.Status.SHIPPED.value,
    VendorOrder.Status.DELIVERED.value,
    VendorOrder.Status.CANCELLED.value,
]
RESERVED = "RESERVED"
PET_SALE_STATUSES = ORDER_STATUSES + [RESERVED]

BUSINESS_PARAM = OpenApiParameter(
    "business",
    OpenApiTypes.UUID,
    description=(
        "Only this business. Leave it out to get every business the vendor owns."
    ),
)


def _items(**lookup):
    """Order items of the vendor order being filtered."""
    return OrderItem.objects.filter(vendor_order=OuterRef("pk"), **lookup)


def _vendor_orders(user, business_id):
    queryset = (
        VendorOrder.objects.filter(business__vendor=user)
        .select_related("order", "order__payment", "order__customer", "business")
        .prefetch_related("items__product", "items__pet")
        .order_by("-created_at", "-id")
    )
    if business_id:
        queryset = queryset.filter(business_id=business_id)
    return queryset


class VendorTransactionListView(generics.ListAPIView):
    """Shared rules: vendors only, optional business filter, optional status."""

    permission_classes = (IsVendor,)
    pagination_class = VendorTransactionPagination
    allowed_statuses = ()

    def business_id(self):
        raw = self.request.query_params.get("business")
        if not raw:
            return None
        try:
            business_id = uuid.UUID(raw)
        except ValueError:
            raise ValidationError({"business": "Not a valid business id."})
        owned = Business.objects.filter(pk=business_id, vendor=self.request.user)
        if not owned.exists():
            raise NotFound("Business not found.")
        return business_id

    def status_value(self):
        value = self.request.query_params.get("status")
        if value and value not in self.allowed_statuses:
            raise ValidationError({"status": "Not a valid status."})
        return value or None


@extend_schema(
    tags=["vendor-transactions"],
    summary="List my merchandise orders",
    description=(
        "Paid orders for merchandise only, newest first. Pet sales and "
        "service bookings are not included."
    ),
    parameters=[
        BUSINESS_PARAM,
        OpenApiParameter(
            "status", str, description="PAID, PROCESSING, SHIPPED, DELIVERED or CANCELLED."
        ),
    ],
)
class VendorOrderTransactionListView(VendorTransactionListView):
    serializer_class = OrderTransactionSerializer
    allowed_statuses = ORDER_STATUSES

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return VendorOrder.objects.none()

        queryset = _vendor_orders(self.request.user, self.business_id())
        queryset = queryset.filter(order__status=Order.Status.PAID).filter(
            Exists(_items(product__isnull=False)),
            ~Exists(_items(pet__isnull=False)),
        )
        status_value = self.status_value()
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset


@extend_schema(
    tags=["vendor-transactions"],
    summary="List my pet sales",
    description=(
        "Paid pet sales, plus pets being held for a customer who has not paid "
        "yet. sale_state is PAID or RESERVED; a reservation also shows "
        "reservation_expires_at. A hold appears only while the pet is "
        "actually reserved and the payment window is still open. Adoption "
        "applications are not included."
    ),
    parameters=[
        BUSINESS_PARAM,
        OpenApiParameter(
            "status",
            str,
            description=(
                "PAID, PROCESSING, SHIPPED, DELIVERED, CANCELLED, or RESERVED "
                "for unpaid holds only."
            ),
        ),
    ],
)
class VendorPetSaleTransactionListView(VendorTransactionListView):
    serializer_class = PetSaleTransactionSerializer
    allowed_statuses = PET_SALE_STATUSES

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return VendorOrder.objects.none()

        queryset = _vendor_orders(self.request.user, self.business_id())
        queryset = queryset.filter(Exists(_items(pet__isnull=False))).annotate(
            has_reserved_pet=Exists(
                _items(pet__adoption_status=Pet.AdoptionStatus.RESERVED)
            )
        )
        paid = Q(order__status=Order.Status.PAID)
        reserved = Q(
            has_reserved_pet=True,
            order__status=Order.Status.PENDING_PAYMENT,
            status=VendorOrder.Status.PENDING_PAYMENT,
            order__expires_at__gt=timezone.now(),
        )
        status_value = self.status_value()
        if status_value == RESERVED:
            return queryset.filter(reserved)
        if status_value:
            return queryset.filter(paid, status=status_value)
        return queryset.filter(paid | reserved)


@extend_schema(
    tags=["vendor-transactions"],
    summary="List my service bookings",
    description=(
        "Service bookings only, newest first. Merchandise orders and pet "
        "sales are not included."
    ),
    parameters=[
        BUSINESS_PARAM,
        OpenApiParameter(
            "status",
            str,
            description="pending, accepted, declined, completed or cancelled.",
        ),
    ],
)
class VendorBookingTransactionListView(VendorTransactionListView):
    serializer_class = BookingTransactionSerializer
    allowed_statuses = Booking.Status.values

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()

        queryset = (
            Booking.objects.filter(service__business__vendor=self.request.user)
            .select_related("customer", "service", "service__business")
            .order_by("-created_at", "-booking_id")
        )
        business_id = self.business_id()
        if business_id:
            queryset = queryset.filter(service__business_id=business_id)
        status_value = self.status_value()
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset
