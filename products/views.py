from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.permissions import ADMIN_ROLES

from .models import Product
from .serializers import ProductSerializer


class ProductPermission(BasePermission):
    """Allow public reads and admin/system-admin writes."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.role in ADMIN_ROLES
        )


class ProductQuerysetMixin:
    """Show inactive products only to administrators."""

    def get_queryset(self):
        queryset = Product.objects.select_related(
            "business",
            "category",
        ).prefetch_related("images")
        user_role = getattr(self.request.user, "role", None)
        if user_role not in ADMIN_ROLES:
            queryset = queryset.filter(is_active=True)

        return queryset


class ProductListCreateView(
    ProductQuerysetMixin,
    generics.ListCreateAPIView,
):
    """List products or create a product as an administrator."""

    serializer_class = ProductSerializer
    permission_classes = (ProductPermission,)


class ProductDetailView(
    ProductQuerysetMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    """Retrieve, update, or deactivate a product."""

    serializer_class = ProductSerializer
    permission_classes = (ProductPermission,)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
