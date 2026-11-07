from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission

from accounts.models import User
from common.permissions import ADMIN_ROLES

from .models import Product
from .serializers import (
    ProductImageUploadSerializer,
    ProductSerializer,
    PublicProductDetailSerializer,
    PublicProductSerializer,
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

        return public_products()


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


def public_products():
    """Products a customer is allowed to see, ready for the public pages."""
    return (
        Product.objects.publicly_visible()
        .select_related("business", "category")
        .prefetch_related("images")
    )


class PublicProductPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


SORT_OPTIONS = {
    "newest": ("-created_at", "-id"),
    "price_asc": ("price", "id"),
    "price_desc": ("-price", "-id"),
}


class PublicProductListView(generics.ListAPIView):
    """Browse merchandise: open to everyone, newest first by default.

    Query params: search, category, business_name, price_min, price_max,
    in_stock=true, sort=newest|price_asc|price_desc.
    """

    serializer_class = PublicProductSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    pagination_class = PublicProductPagination

    def get_decimal_param(self, name):
        value = self.request.query_params.get(name)
        if not value:
            return None

        try:
            return Decimal(value)
        except InvalidOperation:
            raise serializers.ValidationError({name: "Enter a valid number."})

    def get_queryset(self):
        params = self.request.query_params
        queryset = public_products()

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        category = params.get("category")
        if category:
            if not category.isdigit():
                raise serializers.ValidationError(
                    {"category": "Enter a valid category id."}
                )
            queryset = queryset.filter(category_id=int(category))

        business_name = params.get("business_name", "").strip()
        if business_name:
            queryset = queryset.filter(business__name__icontains=business_name)

        price_min = self.get_decimal_param("price_min")
        if price_min is not None:
            queryset = queryset.filter(price__gte=price_min)

        price_max = self.get_decimal_param("price_max")
        if price_max is not None:
            queryset = queryset.filter(price__lte=price_max)

        if params.get("in_stock", "").lower() == "true":
            queryset = queryset.filter(stock_quantity__gt=0)

        sort = params.get("sort", "newest")
        if sort not in SORT_OPTIONS:
            raise serializers.ValidationError(
                {"sort": "Choose newest, price_asc or price_desc."}
            )

        return queryset.order_by(*SORT_OPTIONS[sort])


class PublicProductDetailView(generics.RetrieveAPIView):
    """One product page: open to everyone, same visibility rules as the list."""

    serializer_class = PublicProductDetailSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get_queryset(self):
        return public_products()
