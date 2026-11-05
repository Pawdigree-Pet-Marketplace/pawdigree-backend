from django.shortcuts import render

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsCustomer

from .serializers import CartSerializer
from .services import get_cart_summary


def cart_response(request, status_code=status.HTTP_200_OK):
    """The customer's cart, freshly calculated. Every cart endpoint ends here."""
    summary = get_cart_summary(request.user)
    data = CartSerializer(summary, context={"request": request}).data
    return Response(data, status=status_code)


class CartView(generics.GenericAPIView):
    """The authenticated customer's own cart."""

    serializer_class = CartSerializer
    # Only logged-in customers.     Vendors and admins are turned away.
    permission_classes = (IsAuthenticated, IsCustomer)

    @extend_schema(
        tags=["cart"],
        summary="View my cart",
        description=(
            "Every line with its current price, plus the cart total. "
            "Lines that can't be bought right now are flagged and left out "
            "of the total. Money values are strings, such as \"20.00\"."
        ),
        responses=CartSerializer,
    )
    def get(self, request):
        return cart_response(request)