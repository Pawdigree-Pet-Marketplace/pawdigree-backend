from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from businesses.models import Business

from .models import Product


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


class PublicProductListView(generics.ListAPIView):
    """Browse merchandise: open to everyone, newest first."""

    serializer_class = PublicProductSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    pagination_class = PublicProductPagination

    def get_queryset(self):
        return (
            Product.objects.filter(
                is_active=True,
                category__is_active=True,
                business__is_active=True,
                business__verification_status=Business.VerificationStatus.APPROVED,
            )
            .select_related("business", "category")
            .prefetch_related("images")
            .order_by("-created_at", "-id")
        )