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
