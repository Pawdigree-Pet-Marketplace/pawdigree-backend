from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission

from common.permissions import ADMIN_ROLES

from .models import Category
from .serializers import CategorySerializer


class CategoryPermission(BasePermission):
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


class CategoryQuerysetMixin:
    """Show inactive categories only to administrators."""

    def get_queryset(self):
        queryset = Category.objects.all()
        user_role = getattr(self.request.user, "role", None)

        if user_role not in ADMIN_ROLES:
            queryset = queryset.filter(is_active=True)

        return queryset


class CategoryListCreateView(CategoryQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = CategorySerializer
    permission_classes = (CategoryPermission,)


class CategoryDetailView(CategoryQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CategorySerializer
    permission_classes = (CategoryPermission,)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class PublicCategoryListView(generics.ListAPIView):
    """Active categories for dropdowns, open to everyone.

    ?kind=merchandise|services|pets returns that kind plus general
    categories, because general ones are valid everywhere. ?kind=general
    returns only general categories. Without kind, all active categories.
    """

    serializer_class = CategorySerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    pagination_class = None

    def get_queryset(self):
        queryset = Category.objects.filter(is_active=True)

        kind = self.request.query_params.get("kind")
        if not kind:
            return queryset

        if kind not in Category.Kind.values:
            raise ValidationError(
                {"kind": f"Choose one of: {', '.join(Category.Kind.values)}."}
            )

        if kind == Category.Kind.GENERAL:
            return queryset.filter(kind=Category.Kind.GENERAL)

        return queryset.filter(kind__in=(kind, Category.Kind.GENERAL))