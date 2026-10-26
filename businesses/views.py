from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


from common.permissions import IsAdmin, IsVendor

from .models import Business, BusinessCategory, BusinessDecision
from .serializers import (
    BusinessSerializer,
    BusinessCategoryStatusSerializer,
    BusinessVerificationStatusSerializer,
    BusinessWriteSerializer,
    CategoryRequestSerializer,
    PublicBusinessSerializer,
    VendorResponseSerializer,
)

PARSERS = (MultiPartParser, FormParser, JSONParser)


@extend_schema(request=BusinessWriteSerializer, responses=BusinessSerializer)
class BusinessListCreateView(generics.ListCreateAPIView):
    serializer_class = BusinessSerializer
    permission_classes = (IsVendor,)
    parser_classes = PARSERS

    def get_queryset(self):
        return Business.objects.filter(vendor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(vendor=self.request.user)


@extend_schema(
    tags=["businesses"],
    summary="List approved vendors",
    description=(
        "Public listing of active businesses whose verification status "
        "is approved. Authentication is not required."
    ),
)
class PublicBusinessListView(generics.ListAPIView):
    serializer_class = PublicBusinessSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get_queryset(self):
        approved_categories = BusinessCategory.objects.filter(
            approval_status=BusinessCategory.ApprovalStatus.APPROVED,
            category__is_active=True,
        ).select_related("category")

        queryset = Business.objects.filter(
            verification_status=Business.VerificationStatus.APPROVED,
            is_active=True,
        ).prefetch_related(
            Prefetch(
                "business_categories",
                queryset=approved_categories,
            )
        )

        search = self.request.query_params.get("search", "").strip()
        city_district = self.request.query_params.get(
            "city_district", ""
        ).strip()
        category = self.request.query_params.get("category", "").strip()

        if search:
            queryset = queryset.filter(name__icontains=search)

        if city_district:
            queryset = queryset.filter(
                city_district__icontains=city_district
            )

        if category:
            queryset = queryset.filter(
                Q(
                    business_categories__category__name__iexact=category
                )
                | Q(
                    business_categories__category__slug__iexact=category
                ),
                business_categories__approval_status=(
                    BusinessCategory.ApprovalStatus.APPROVED
                ),
                business_categories__category__is_active=True,
            )

        return queryset.distinct()


class BusinessDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = BusinessSerializer
    permission_classes = (IsVendor,)
    parser_classes = PARSERS

    def get_queryset(self):
        return Business.objects.filter(vendor=self.request.user)

    def perform_update(self, serializer):
        serializer.save(
            verification_status=Business.VerificationStatus.PENDING,
            reviewed_at=None,
        )


@extend_schema(
    tags=['businesses'],
    summary="Register a business",
    description=(
        "Creates a business owned by the authenticated vendor. "
        "The vendor is taken from the access token."
    ),
    request=BusinessWriteSerializer,
    responses=BusinessSerializer,
)
class BusinessRegistrationView(generics.CreateAPIView):
    """Registration endpoint, mounted by accounts at its existing URL."""

    serializer_class = BusinessSerializer
    permission_classes = (IsVendor,)
    parser_classes = PARSERS

    def perform_create(self, serializer):
        serializer.save(vendor=self.request.user)


@extend_schema(
    tags=["businesses"],
    summary="Vendor verification status",
    description=(
        "Lists the authenticated vendor's businesses with their "
        "verification status, the administrator's decision, and the "
        "approval status of each requested category. A vendor can sell "
        "under a category only when the business and that category are "
        "both approved."
    ),
)
class BusinessVerificationStatusView(generics.ListAPIView):
    serializer_class = BusinessVerificationStatusSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        return Business.objects.filter(
            vendor=self.request.user
        ).prefetch_related(
            Prefetch(
                "business_categories",
                queryset=BusinessCategory.objects.select_related(
                    "category", "business"
                ),
            )
        )
class VendorBusinessResponseView(generics.GenericAPIView):
    serializer_class = VendorResponseSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        return Business.objects.filter(vendor=self.request.user)

    def post(self, request, *args, **kwargs):
        business = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        business.vendor_response = serializer.validated_data["vendor_response"]
        business.save(update_fields=["vendor_response", "updated_at"])

        return Response(
            {
                "id": str(business.pk),
                "vendor_response": business.vendor_response,
            },
            status=status.HTTP_200_OK,
        )


class BusinessCategoryRequestView(generics.GenericAPIView):
    """Allow a vendor to request categories for their own business."""

    serializer_class = CategoryRequestSerializer
    permission_classes = (IsVendor,)

    def post(self, request, business_id):
        business = get_object_or_404(
            Business,
            pk=business_id,
            vendor=request.user,
        )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        requested_categories = serializer.validated_data["category_ids"]
        saved_categories = []

        for category in requested_categories:
            business_category, _ = BusinessCategory.objects.get_or_create(
                business=business,
                category=category,
            )
            saved_categories.append(business_category)

        response_serializer = BusinessCategoryStatusSerializer(
            saved_categories,
            many=True,
        )

        return Response(
            {
                "message": "Category requests submitted successfully.",
                "categories": response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )
