from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from common.permissions import IsVendor

from .models import Business, BusinessCategory
from .serializers import (
    BusinessSerializer,
    BusinessVerificationStatusSerializer,
    BusinessWriteSerializer,
    CategoryRequestSerializer,
)
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response

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


class BusinessDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = BusinessSerializer
    permission_classes = (IsVendor,)
    parser_classes = PARSERS

    def get_queryset(self):
        return Business.objects.filter(vendor=self.request.user)


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
    
class BusinessCategoryRequestView(generics.GenericAPIView):
    """Allow a vendor to request categories for their own business."""

    serializer_class = CategoryRequestSerializer
    permission_classes = (IsVendor,)

    def post(self, request, business_id):
        # Vendors can only access businesses they own.
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

        from .serializers import BusinessCategoryStatusSerializer

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
