from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import User
from common.permissions import ADMIN_ROLES

from .models import Product
from .public import visible_products
from .serializers import (
    ProductImageUploadSerializer,
    ProductSerializer,
    VendorProductSerializer,
)

MAX_PRODUCT_IMAGES = 5


class ProductPermission(BasePermission):
    """Allow public reads and vendor/admin product management."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.role in (*ADMIN_ROLES, User.Role.VENDOR)
        )


class ProductQuerysetMixin:
    """Filter products based on user role and ownership."""

    def get_queryset(self):
        queryset = Product.objects.select_related(
            "business",
            "category",
        ).prefetch_related("images")
        user = self.request.user
        user_role = getattr(user, "role", None)
        if user_role in ADMIN_ROLES:
            return queryset
        if user_role == User.Role.VENDOR:
            return queryset.filter(business__vendor=user)

        return visible_products()


class ProductListCreateView(
    ProductQuerysetMixin,
    generics.ListCreateAPIView,
):
    """List products or create products for vendors and administrators."""

    serializer_class = ProductSerializer
    permission_classes = (ProductPermission,)

    def get_serializer_class(self):
        user_role = getattr(self.request.user, "role", None)
        if user_role == User.Role.VENDOR:
            return VendorProductSerializer
        return ProductSerializer


class ProductDetailView(
    ProductQuerysetMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    """Retrieve, update, or deactivate a product."""

    serializer_class = ProductSerializer
    permission_classes = (ProductPermission,)

    def get_serializer_class(self):
        user_role = getattr(self.request.user, "role", None)
        if user_role == User.Role.VENDOR:
            return VendorProductSerializer
        return ProductSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


def get_manageable_product(request, product_pk):
    """Return a product the user may manage: a vendor's own, or any for admins."""
    products = Product.objects.all()
    if request.user.role == User.Role.VENDOR:
        products = products.filter(business__vendor=request.user)

    return get_object_or_404(products, pk=product_pk)


class ProductImageCreateView(generics.CreateAPIView):
    """Add an image to a product. The first image is the main image."""

    serializer_class = ProductImageUploadSerializer
    permission_classes = (ProductPermission,)
    parser_classes = (MultiPartParser, FormParser)

    def perform_create(self, serializer):
        product = get_manageable_product(
            self.request,
            self.kwargs["product_pk"],
        )
        if product.images.count() >= MAX_PRODUCT_IMAGES:
            raise ValidationError(
                {
                    "image": (
                        f"A product can have at most {MAX_PRODUCT_IMAGES} images."
                    )
                }
            )

        serializer.save(product=product)


class ProductImageDeleteView(generics.DestroyAPIView):
    """Remove one image from a product."""

    serializer_class = ProductImageUploadSerializer
    permission_classes = (ProductPermission,)

    def get_object(self):
        product = get_manageable_product(
            self.request,
            self.kwargs["product_pk"],
        )
        return get_object_or_404(product.images, pk=self.kwargs["pk"])