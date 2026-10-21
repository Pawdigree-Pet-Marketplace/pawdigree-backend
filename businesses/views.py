from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.permissions import IsVendor

from .models import Business, BusinessCategory
from .serializers import (
    BusinessSerializer,
    BusinessVerificationStatusSerializer,
    BusinessWriteSerializer,
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
        return Business.objects.filter(
            verification_status=Business.VerificationStatus.APPROVED,
            is_active=True,
        )


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
