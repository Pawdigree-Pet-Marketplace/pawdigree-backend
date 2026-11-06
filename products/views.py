from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import User
from businesses.models import Business
from common.permissions import ADMIN_ROLES

from .models import Product
from .serializers import ProductSerializer, VendorProductSerializer


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

        return queryset.filter(
            is_active=True,
            category__is_active=True,
            business__is_active=True,
            business__verification_status=Business.VerificationStatus.APPROVED,
        )


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
