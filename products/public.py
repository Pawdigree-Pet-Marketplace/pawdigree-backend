from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from businesses.models import Business

from .models import Product
from .serializers import ProductImageSerializer


class PublicProductPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


class PublicProductSerializer(serializers.ModelSerializer):
    """What a customer sees on the merchandise page."""

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    business_name = serializers.CharField(
        source="business.name",
        read_only=True,
    )
    is_available = serializers.BooleanField(read_only=True)
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "price",
            "category",
            "category_name",
            "business_name",
            "is_available",
            "main_image",
        )

    def get_main_image(self, obj):
        first = next(iter(obj.images.all()), None)
        if first is None:
            return None

        request = self.context.get("request")
        url = first.image.url
        return request.build_absolute_uri(url) if request else url


class PublicProductDetailSerializer(PublicProductSerializer):
    """The full product page: the list fields plus description and images."""

    images = ProductImageSerializer(many=True, read_only=True)

    class Meta(PublicProductSerializer.Meta):
        fields = PublicProductSerializer.Meta.fields + (
            "description",
            "images",
        )


def visible_products():
    """Products a customer is allowed to see."""
    return (
        Product.objects.filter(
            is_active=True,
            category__is_active=True,
            business__is_active=True,
            business__verification_status=Business.VerificationStatus.APPROVED,
        )
        .select_related("business", "category")
        .prefetch_related("images")
    )


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
        queryset = visible_products()

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
        return visible_products()