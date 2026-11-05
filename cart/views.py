from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.settings import api_settings

from .permissions import IsCustomerOrGuest
from .serializers import AddToCartSerializer, CartSerializer
from .services import (
    GUEST_HEADER,
    add_to_cart,
    get_cart_summary,
    owner_from_request,
)
from .throttles import GuestAddThrottle

# Shown in the API docs for every endpoint that accepts it.
GUEST_TOKEN_PARAMETER = OpenApiParameter(
    name=GUEST_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "Guests only: the cart_token returned when the guest first added "
        "something. Ignored for logged-in customers."
    ),
)


def cart_response(request, status_code=status.HTTP_200_OK, token=None):
    """The visitor's cart, freshly calculated. Every cart endpoint ends here."""
    summary = get_cart_summary(owner_from_request(request))
    summary.cart_token = token
    data = CartSerializer(summary, context={"request": request}).data
    return Response(data, status=status_code)


class CartView(generics.GenericAPIView):
    """The visitor's own cart."""

    serializer_class = CartSerializer
    permission_classes = (IsCustomerOrGuest,)

    @extend_schema(
        tags=["cart"],
        summary="View my cart",
        description=(
            "Every line with its current price, plus the cart total. "
            "Lines that can't be bought right now are flagged and left out "
            "of the total. Money values are strings, such as \"20.00\"."
        ),
        parameters=[GUEST_TOKEN_PARAMETER],
        responses=CartSerializer,
    )
    def get(self, request):
        return cart_response(request)


class CartItemCreateView(generics.GenericAPIView):
    """Add a product to the visitor's cart."""

    serializer_class = AddToCartSerializer
    permission_classes = (IsCustomerOrGuest,)
    # Keep any project-wide throttles and add the guest limit.
    throttle_classes = (*api_settings.DEFAULT_THROTTLE_CLASSES, GuestAddThrottle)

    @extend_schema(
        tags=["cart"],
        summary="Add a product to my cart",
        description=(
            "Adds the product, or raises its quantity if it is already in "
            "the cart. Returns the whole cart with fresh totals: 201 when a "
            "new line was created, 200 when a quantity went up. A guest's "
            "response includes cart_token: keep it and send it in the "
            "X-Cart-Token header on every later call."
        ),
        parameters=[GUEST_TOKEN_PARAMETER],
        request=AddToCartSerializer,
        responses={201: CartSerializer, 200: CartSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart, created = add_to_cart(
            owner=owner_from_request(request),
            product_id=serializer.validated_data["product"],
            quantity=serializer.validated_data["quantity"],
        )

        return cart_response(
            request,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            token=cart.guest_token,
        )