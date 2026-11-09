from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from common.permissions import IsCustomer

from .models import Order
from .serializers import CheckoutSerializer, OrderSerializer
from .services import checkout


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
