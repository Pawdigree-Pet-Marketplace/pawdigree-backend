import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from businesses.models import Business
from common.permissions import ADMIN_ROLES, IsAdmin, IsVendor

from .models import Product
from .notifications import notify_listing_approved, notify_listing_rejected
from .serializers import (
    ProductImageUploadSerializer,
    ProductRejectSerializer,
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
        if self.request.user.role == User.Role.VENDOR:
            product.send_back_for_review()


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

    def perform_destroy(self, instance):
        product = instance.product
        instance.delete()
        if self.request.user.role == User.Role.VENDOR:
            product.send_back_for_review()


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


@extend_schema(
    tags=["products"],
    summary="List products waiting for review (administrators)",
    description="Active products that are neither approved nor rejected, oldest first.",
)
class AdminPendingProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (IsAdmin,)
    pagination_class = PublicProductPagination

    def get_queryset(self):
        return (
            Product.objects.pending_review()
            .select_related("business", "category")
            .prefetch_related("images")
            .order_by("created_at")
        )


class AdminProductReviewBaseView(generics.GenericAPIView):
    serializer_class = ProductSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True)
            .select_related("business__vendor", "category")
            .prefetch_related("images")
        )


@extend_schema(
    tags=["products"],
    summary="Approve a product (administrators)",
    request=None,
    description="Makes the product public and notifies the vendor.",
)
class AdminProductApproveView(AdminProductReviewBaseView):
    @transaction.atomic
    def post(self, request, pk):
        product = self.get_object()

        if product.approved:
            raise serializers.ValidationError("This product is already approved.")

        product.approved = True
        product.rejection_reason = ""
        product.reviewed_by = request.user
        product.reviewed_at = timezone.now()
        product.save(
            update_fields=[
                "approved",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        # Notify only if the database change actually committed.
        transaction.on_commit(lambda: notify_listing_approved(product))

        return Response(self.get_serializer(product).data)


@extend_schema(
    tags=["products"],
    summary="Reject a product (administrators)",
    request=ProductRejectSerializer,
    description=(
        "Hides the product, stores the reason and notifies the vendor. "
        "The vendor can edit the product to send it for review again."
    ),
)
class AdminProductRejectView(AdminProductReviewBaseView):
    @transaction.atomic
    def post(self, request, pk):
        product = self.get_object()

        if not product.approved and product.rejection_reason:
            raise serializers.ValidationError("This product is already rejected.")

        data = ProductRejectSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        product.approved = False
        product.rejection_reason = data.validated_data["reason"]
        product.reviewed_by = request.user
        product.reviewed_at = timezone.now()
        product.save(
            update_fields=[
                "approved",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        transaction.on_commit(lambda: notify_listing_rejected(product))

        return Response(self.get_serializer(product).data)


BULK_MAX_ROWS = 200
BULK_MAX_FILE_BYTES = 5 * 1024 * 1024
BULK_COLUMNS = (
    "business_id",
    "category_id",
    "name",
    "description",
    "price",
    "stock_quantity",
)
BULK_REQUIRED_COLUMNS = ("category_id", "name", "price")


@extend_schema(
    tags=["products"],
    summary="Bulk upload merchandise (vendors)",
    description=(
        "Upload a CSV file to create many products at once. Every row is "
        "validated with the same rules as a single product. Valid rows are "
        "created as unapproved products and stay hidden from customers "
        "until an administrator approves them; "
        "invalid rows are returned with the row number and the errors. "
        "business_id can be left blank if the vendor owns exactly one "
        "approved Pet Merchandise business."
    ),
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {"file": {"type": "string", "format": "binary"}},
            "required": ["file"],
        }
    },
    responses={
        200: inline_serializer(
            name="ProductBulkUploadResult",
            fields={
                "created": serializers.IntegerField(),
                "failed": serializers.ListField(child=serializers.DictField()),
            },
        ),
        400: OpenApiResponse(
            description="Whole-file problem (see the 'file' error message)."
        ),
    },
)
class ProductBulkUploadView(APIView):
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request):
        upload = request.FILES.get("file")

        if upload is None:
            raise serializers.ValidationError({"file": "No file was uploaded."})
        if not upload.name.lower().endswith(".csv"):
            raise serializers.ValidationError({"file": "Please upload a .csv file."})
        if upload.size > BULK_MAX_FILE_BYTES:
            raise serializers.ValidationError({"file": "File must be under 5MB."})

        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise serializers.ValidationError(
                {"file": "File must be saved as UTF-8 CSV."}
            ) from None

        reader = csv.DictReader(io.StringIO(text))
        reader.fieldnames = [
            (name or "").strip().lower() for name in (reader.fieldnames or [])
        ]

        missing = [c for c in BULK_REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise serializers.ValidationError(
                {"file": f"Missing columns: {', '.join(missing)}."}
            )

        rows = list(reader)
        if not rows:
            raise serializers.ValidationError({"file": "The file has no rows."})
        if len(rows) > BULK_MAX_ROWS:
            raise serializers.ValidationError(
                {"file": f"At most {BULK_MAX_ROWS} rows per upload."}
            )

        # A vendor with exactly one approved, active Pet Merchandise business
        # doesn't need to fill business_id.
        eligible = list(
            Business.objects.filter(
                vendor=request.user,
                is_active=True,
                verification_status=Business.VerificationStatus.APPROVED,
                business_type=Business.BusinessType.PRODUCT_SELLER,
            )
        )
        default_business = eligible[0] if len(eligible) == 1 else None

        valid_serializers = []
        failed = []

        # Row 1 is the header, so data starts at row 2 (matches the spreadsheet).
        for row_number, row in enumerate(rows, start=2):
            data = {
                key: (value or "").strip()
                for key, value in row.items()
                if key in BULK_COLUMNS
            }
            data = {key: value for key, value in data.items() if value}

            if not data:
                continue  # skip completely empty rows

            if "business_id" in data:
                data["business"] = data.pop("business_id")
            elif default_business:
                data["business"] = default_business.pk

            if "category_id" in data:
                data["category"] = data.pop("category_id")

            serializer = VendorProductSerializer(
                data=data, context={"request": request}
            )

            if serializer.is_valid():
                valid_serializers.append(serializer)
            else:
                failed.append({"row": row_number, "errors": serializer.errors})

        for serializer in valid_serializers:
            serializer.save()

        return Response({"created": len(valid_serializers), "failed": failed})


@extend_schema(
    tags=["products"],
    summary="Download the merchandise bulk upload CSV template",
    description=(
        "Public CSV template with the required columns and two example "
        "rows. category_id values must come from GET /api/categories/, "
        "using a merchandise or general category."
    ),
    responses={(200, "text/csv"): OpenApiTypes.STR},
)
class ProductBulkTemplateView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        lines = [
            ",".join(BULK_COLUMNS),
            ",1,Dog Leash,Durable nylon leash 1.5m,25000,40",
            ",1,Cat Scratching Post,Sisal rope post 60cm,85000,15",
        ]
        response = HttpResponse("\n".join(lines) + "\n", content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="product_bulk_upload_template.csv"'
        )
        return response
