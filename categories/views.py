from rest_framework import generics

from common.permissions import ADMIN_ROLES, IsAdminOrReadOnly

from .models import Category
from .serializers import CategorySerializer


class CategoryQuerysetMixin:
    """Show inactive categories only to administrators."""

    def get_queryset(self):
        queryset = Category.objects.all()

        if self.request.user.role not in ADMIN_ROLES:
            queryset = queryset.filter(is_active=True)

        return queryset


class CategoryListCreateView(CategoryQuerysetMixin, generics.ListCreateAPIView):
    serializer_class = CategorySerializer
    permission_classes = (IsAdminOrReadOnly,)


class CategoryDetailView(CategoryQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CategorySerializer
    permission_classes = (IsAdminOrReadOnly,)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])