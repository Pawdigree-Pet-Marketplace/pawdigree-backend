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
from .services import sync_vendor_approval
from .models import Business, BusinessCategory, BusinessDecision
from .serializers import (
    BusinessSerializer,
    BusinessCategoryStatusSerializer,
    BusinessVerificationStatusSerializer,
    BusinessWriteSerializer,
    CategoryRequestSerializer,
    PublicBusinessSerializer,
    VendorResponseSerializer,
    BusinessDecisionHistorySerializer,
    BusinessDecisionInputSerializer,
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
        
        
@extend_schema(
    tags=["businesses"],
    summary="Decide on a vendor application (administrators)",
    request=BusinessDecisionInputSerializer,
    description=(
        "Actions: approve (from pending), request_changes (from pending or "
        "approved, reason required), suspend (from approved, reason required) "
        "and reapprove (from suspended). The decision and reason are saved "
        "on the business and in its decision history, and the vendor's "
        "approved flag is updated."
    ),
)
class AdminBusinessDecisionView(generics.GenericAPIView):
    serializer_class = BusinessDecisionInputSerializer
    permission_classes = (IsAdmin,)

    @transaction.atomic
    def post(self, request, pk):
        # Lock the row so two admins can't decide on the same state at once.
        business = get_object_or_404(Business.objects.select_for_update(), pk=pk)

        serializer = BusinessDecisionInputSerializer(
            data=request.data,
            context={"business": business},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        reason = data.get("reason", "")

        business.verification_status = data["to_status"]
        business.decision_reason = reason
        business.reviewed_at = timezone.now()
        business.save(update_fields=[
            "verification_status", "decision_reason", "reviewed_at", "updated_at",
        ])

        decision = BusinessDecision.objects.create(
            business=business,
            decided_by=request.user,
            action=data["action"],
            from_status=data["from_status"],
            to_status=data["to_status"],
            reason=reason,
        )

        vendor_approved = sync_vendor_approval(business.vendor)

        return Response({
            "business_id": str(business.pk),
            "verification_status": business.verification_status,
            "vendor_approved": vendor_approved,
            "decision": BusinessDecisionHistorySerializer(decision).data,
        })


@extend_schema(
    tags=["businesses"],
    summary="Decision history for a business (administrators)",
)
class AdminBusinessDecisionHistoryView(generics.ListAPIView):
    serializer_class = BusinessDecisionHistorySerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BusinessDecision.objects.none()

        business = get_object_or_404(Business, pk=self.kwargs["pk"])
        return business.decisions.select_related("decided_by")
