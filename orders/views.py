
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.permissions import IsCustomer, IsVendor

from .models import Order, VendorOrder
from .serializers import (
    CheckoutSerializer,
    OrderSerializer,
    VendorOrderDetailSerializer,
    VendorOrderStatusSerializer,
)
from .services import change_status, checkout


class CheckoutView(generics.GenericAPIView):
    """Turn the customer's cart into an order that is waiting for payment."""

    serializer_class = CheckoutSerializer
    permission_classes = (IsCustomer,)

    @extend_schema(
        tags=["orders"],
        summary="Check out my cart",
        description=(
            "Creates one order for the whole cart, split into one vendor "
            "order per business, and reserves the stock. The customer has "
            "until expires_at to pay (10 minutes). If they don't, the order "
            "expires and the stock is released. The cart is left untouched "
            "until payment is confirmed, so after an expiry the customer "
            "lands back on a cart that still has their items. Starting a new "
            "checkout cancels the customer's earlier unpaid order. Money "
            "values are strings, such as \"20.00\"."
        ),
        request=CheckoutSerializer,
        responses={201: OrderSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = checkout(request.user, dict(serializer.validated_data))

        order = Order.objects.prefetch_related(
            "vendor_orders__business",
            "vendor_orders__items__product",
        ).get(pk=order.pk)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class CustomerOrderListView(generics.ListAPIView):
    """List the authenticated customer's own orders."""

    serializer_class = OrderSerializer
    permission_classes = (IsCustomer,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()

        return (
            Order.objects.filter(customer=self.request.user)
            .prefetch_related(
                "vendor_orders__business",
                "vendor_orders__items__product",
            )
            .order_by("-created_at")
        )

    @extend_schema(
        tags=["orders"],
        summary="List my orders",
        description=(
            "Returns the authenticated customer's orders, newest first, "
            "including vendor orders, purchased products and their statuses."
        ),
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    
class CustomerOrderDetailView(generics.RetrieveAPIView):
    """Retrieve one order belonging to the authenticated customer."""

    serializer_class = OrderSerializer
    permission_classes = (IsCustomer,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()

        return (
            Order.objects.filter(customer=self.request.user)
            .prefetch_related(
                "vendor_orders__business",
                "vendor_orders__items__product",
            )
        )

    @extend_schema(
        tags=["orders"],
        summary="Retrieve my order details",
        description=(
            "Returns one order belonging to the authenticated customer, "
            "including its shipping details, vendor orders, purchased "
            "products, quantities, prices and statuses. Customers cannot "
            "retrieve another customer's order."
        ),
        responses={200: OrderSerializer},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)



class VendorOrderListView(generics.ListAPIView):
    """The paid orders that contain the vendor's own products."""

    serializer_class = VendorOrderDetailSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return VendorOrder.objects.none()

        queryset = (
            VendorOrder.objects.filter(
                business__vendor=self.request.user,
                order__status=Order.Status.PAID,
            )
            .select_related("order", "business")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in VendorOrder.Status.values:
                raise ValidationError({"status": "Not a valid order status."})
            queryset = queryset.filter(status=status_filter)
        return queryset

    @extend_schema(
        tags=["orders"],
        summary="List my orders",
        description=(
            "Paid orders that contain the vendor's own products, newest "
            "first, with the delivery details needed to ship them. Orders "
            "that are unpaid or expired are not shown."
        ),
        parameters=[
            OpenApiParameter(
                "status",
                str,
                description="Only show orders with this status, e.g. PROCESSING.",
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class VendorOrderStatusView(generics.GenericAPIView):
    """Move one of the vendor's orders to its next status."""

    serializer_class = VendorOrderStatusSerializer
    permission_classes = (IsVendor,)

    @extend_schema(
        tags=["orders"],
        summary="Change the status of my order",
        description=(
            "A paid order moves PAID to PROCESSING to SHIPPED to DELIVERED. "
            "It can be cancelled while it is PAID or PROCESSING, which puts "
            "the stock back. Any other move is refused."
        ),
        request=VendorOrderStatusSerializer,
        responses={200: VendorOrderDetailSerializer},
    )
    def patch(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vendor_order = change_status(
            pk, serializer.validated_data["status"], request.user
        )

        vendor_order = (
            VendorOrder.objects.select_related("order", "business")
            .prefetch_related("items__product")
            .get(pk=vendor_order.pk)
        )
        return Response(VendorOrderDetailSerializer(vendor_order).data)
