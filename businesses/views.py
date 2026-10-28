from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, serializers
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
    AdminBusinessReviewSerializer,
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
        # Editing a live or under-review business sends it back for review.
        # Drafts stay drafts until submitted, and suspended or rejected
        # businesses can't reopen themselves by editing.
        goes_back_to_review = (
            Business.VerificationStatus.PENDING,
            Business.VerificationStatus.CHANGES_REQUESTED,
            Business.VerificationStatus.APPROVED,
        )
        if serializer.instance.verification_status in goes_back_to_review:
            serializer.save(
                verification_status=Business.VerificationStatus.PENDING,
                reviewed_at=None,
            )
        else:
            serializer.save()

        sync_vendor_approval(self.request.user)


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

        if business.verification_status != Business.VerificationStatus.CHANGES_REQUESTED:
            raise serializers.ValidationError(
                "There are no requested changes to respond to."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        business.vendor_response = serializer.validated_data["vendor_response"]
        business.verification_status = Business.VerificationStatus.PENDING
        business.reviewed_at = None
        business.save(update_fields=[
            "vendor_response", "verification_status", "reviewed_at", "updated_at",
        ])

        return Response(
            {
                "id": str(business.pk),
                "vendor_response": business.vendor_response,
                "verification_status": business.verification_status,
            },
            status=status.HTTP_200_OK,
        )

class BusinessCategoryRequestView(generics.GenericAPIView):
    """Allow a vendor to request categories for their own business."""

    serializer_class = CategoryRequestSerializer
    permission_classes = (IsVendor,)

    # A suspended or rejected business can't ask for new categories.
    BLOCKED_STATUSES = (
        Business.VerificationStatus.SUSPENDED,
        Business.VerificationStatus.REJECTED,
    )

    @transaction.atomic
    def post(self, request, business_id):
        # Lock the business, so an admin decision can't change its status
        # while this request is half done.
        business = get_object_or_404(
            Business.objects.select_for_update(),
            pk=business_id,
            vendor=request.user,
        )

        if not business.is_active:
            raise serializers.ValidationError(
                "This business is inactive, so it can't request categories."
            )

        if business.verification_status in self.BLOCKED_STATUSES:
            raise serializers.ValidationError(
                "You can't request categories while this business is "
                f"{business.verification_status.replace('_', ' ')}."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        saved_categories = []
        created = 0
        reopened = 0

        for category in serializer.validated_data["category_ids"]:
            business_category, was_created = (
                BusinessCategory.objects.get_or_create(
                    business=business,
                    category=category,
                )
            )

            if was_created:
                created += 1
            elif (
                business_category.approval_status
                == BusinessCategory.ApprovalStatus.REJECTED
            ):
                # Applying again after a rejection sends it back for review.
                business_category.approval_status = (
                    BusinessCategory.ApprovalStatus.PENDING
                )
                business_category.save(
                    update_fields=["approval_status", "updated_at"]
                )
                reopened += 1

            saved_categories.append(business_category)

        changed = created + reopened

        sent_back = False
        if (
            changed
            and business.verification_status
            == Business.VerificationStatus.APPROVED
        ):
            # New categories mean the business is reviewed again.
            business.verification_status = Business.VerificationStatus.PENDING
            business.reviewed_at = None
            business.save(update_fields=[
                "verification_status", "reviewed_at", "updated_at",
            ])
            sync_vendor_approval(business.vendor)
            sent_back = True

        if not changed:
            message = (
                "These categories were already requested. "
                "No changes were made."
            )
        elif sent_back:
            message = (
                f"{changed} category request(s) sent. Your business is back "
                "in review until they are decided."
            )
        else:
            message = f"{changed} category request(s) sent for review."

        response_serializer = BusinessCategoryStatusSerializer(
            saved_categories,
            many=True,
        )

        return Response(
            {
                "message": message,
                "new_requests": created,
                "reopened": reopened,
                "sent_back_to_review": sent_back,
                "verification_status": business.verification_status,
                "categories": response_serializer.data,
            },
            status=(
                status.HTTP_201_CREATED if changed else status.HTTP_200_OK
            ),
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


@extend_schema(
    tags=["businesses"],
    summary="Submit a business for review",
    request=None,
    responses=BusinessVerificationStatusSerializer,
    description=(
        "Moves a draft business to pending so administrators can review it. "
        "After requested changes, use the response endpoint instead."
    ),
)
class BusinessSubmitView(generics.GenericAPIView):
    serializer_class = BusinessVerificationStatusSerializer
    permission_classes = (IsVendor,)

    @transaction.atomic
    def post(self, request, pk):
        business = get_object_or_404(
            Business.objects.select_for_update(),
            pk=pk,
            vendor=request.user,
        )

        if business.verification_status != Business.VerificationStatus.DRAFT:
            raise serializers.ValidationError(
                "Only a draft business can be submitted for review."
            )

        business.verification_status = Business.VerificationStatus.PENDING
        business.reviewed_at = None
        business.save(update_fields=[
            "verification_status", "reviewed_at", "updated_at",
        ])

        return Response(BusinessVerificationStatusSerializer(business).data)
    
    
    
class AdminBusinessPagination(PageNumberPagination):
        page_size = 20


def admin_business_queryset():
    return Business.objects.select_related("vendor").prefetch_related(
        "images",
        Prefetch(
            "business_categories",
            queryset=BusinessCategory.objects.select_related("category", "business"),
        ),
    )


@extend_schema(
    tags=["businesses"],
    summary="List vendor applications (administrators)",
    description=(
        "Defaults to applications waiting for review, oldest first. "
        "Use ?status= with a verification status, or all."
    ),
    parameters=[
        OpenApiParameter(
            "status",
            str,
            description=(
                "pending (default), changes_requested, approved, suspended, "
                "rejected, draft or all."
            ),
        ),
    ],
)
class AdminBusinessListView(generics.ListAPIView):
    serializer_class = AdminBusinessReviewSerializer
    permission_classes = (IsAdmin,)
    pagination_class = AdminBusinessPagination

    def get_queryset(self):
        queryset = admin_business_queryset().order_by("created_at")
        value = self.request.query_params.get("status", "pending").strip().lower()

        if value == "all":
            return queryset

        if value not in Business.VerificationStatus.values:
            raise serializers.ValidationError({
                "status": (
                    "Choose one of: all, "
                    + ", ".join(Business.VerificationStatus.values) + "."
                )
            })

        return queryset.filter(verification_status=value)


@extend_schema(
    tags=["businesses"],
    summary="Review one vendor application (administrators)",
)
class AdminBusinessDetailView(generics.RetrieveAPIView):
    serializer_class = AdminBusinessReviewSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return admin_business_queryset()
    
    
    
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

@extend_schema(
    tags=["businesses"],
    summary="Withdraw a business from review",
    request=None,
    responeses=BusinessVerificationStatusSerializer,
    description=(
        "Moves a pending business back to draft. Submit it again when "
        "vendor is ready."
    ),
)

class BusinessWithdrawView(generics.GenericAPIView):
    serializer_class = BusinessVerificationStatusSerializer
    permission_classes = (IsVendor,)
    
    @transaction.atomic
    def post(self, request, pk):
        # Look only among this vendor's own businesses, so someone else's
        # business returns 404. select_for_update() locks the row until the
        # request ends, so an admin decision can't change it meanwhile.
        business = get_object_or_404(
            Business.objects.select_for_update(),
            pk=pk,
            vendor=request.user,
        )
        
        # Only a business that is waiting for review can be withdrawn.
        if business.verification_status != Business.VerificationStatus.PENDING:
            raise serializers.ValidationError (
                "Only a business waiting for review can be withdrawn."
            )
        
        # Back to draft. No review is waiting, so clear the review date.
        business.verification_status = Business.VerificationStatus.DRAFT  
        business.reviewed_at = None
        
        # update_fields writes only these columns. updated_at must be listed,
        # because auto_now only refreshes fields that are being saved.
        business.save(update_fields=["verification_status", "reviewd_at", "updated_at"])
        
        return Response(BusinessVerificationStatusSerializer(business).data)
    

class BusinessResubmitBaseView(generics.GenericAPIView):
    """Shared logic for a vendor sending a business back to review.

    A subclass sets from_status (the status the business must be in) and
    error_message (shown when it is in any other status). This class is not
    given a URL, so only its subclasses are reachable.
    """

    serializer_class = VendorResponseSerializer
    permission_classes = (IsVendor,)

    from_status = None
    error_message = ""

    @transaction.atomic
    def post(self, request, pk):
        # Own business only, row locked for the length of the request.
        business = get_object_or_404(
            Business.objects.select_for_update(),
            pk=pk,
            vendor=request.user,
        )

        # The subclass decides which status this move starts from.
        if business.verification_status != self.from_status:
            raise serializers.ValidationError(self.error_message)

        # The vendor must explain why the business should be reconsidered.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # decision_reason is left alone, so the admin's earlier reason
        # stays on record next to the vendor's reply.
        business.vendor_response = serializer.validated_data["vendor_response"]
        business.verification_status = Business.VerificationStatus.PENDING
        business.reviewed_at = None
        business.save(update_fields=[
            "vendor_response", "verification_status",
            "reviewed_at", "updated_at",
        ])

        return Response(BusinessVerificationStatusSerializer(business).data)


@extend_schema(
    tags=["businesses"],
    summary="Appeal a suspension",
    request=VendorResponseSerializer,
    responses=BusinessVerificationStatusSerializer,
    description=(
        "Sends a suspended business back to pending, with a message for "
        "the administrator. The suspension reason stays on record."
    ),
)
class BusinessAppealView(BusinessResubmitBaseView):
    from_status = Business.VerificationStatus.SUSPENDED
    error_message = "Only a suspended business can appeal a suspension."
        