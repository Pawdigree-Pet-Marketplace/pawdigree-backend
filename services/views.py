from django.db.models import F
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from businesses.models import Business, BusinessCategory
from categories.models import Category
from common.permissions import IsAdmin, IsVendor

from .models import Service, AvailabilitySlot
from .filters import filter_public_services
from .notifications import notify_listing_approved, notify_listing_rejected
from .serializers import (
    AvailabilitySlotSerializer,
    ServiceSerializer,
    ServiceUpdateSerializer,
    ServiceCalendarSerializer,
    PublicServiceSerializer,
    ServiceRejectSerializer,
)


class PublicServicePagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


def public_services():
    """Services available to customers through an approved business category."""
    return (
        Service.objects.filter(
            approved=True,
            is_active=True,
            business__is_active=True,
            business__verification_status=Business.VerificationStatus.APPROVED,
            category__is_active=True,
            category__kind__in=(Category.Kind.SERVICES, Category.Kind.GENERAL),
            business__business_categories__category_id=F("category_id"),
            business__business_categories__approval_status=(
                BusinessCategory.ApprovalStatus.APPROVED
            ),
        )
        .select_related("business", "category")
    )


@extend_schema_view(
    get=extend_schema(
        tags=["services"],
        summary="List my services",
        description=(
            "Lists all active services belonging to businesses "
            "owned by the authenticated vendor."
        ),
        responses={200: ServiceSerializer(many=True)},
    ),
    post=extend_schema(
        tags=["services"],
        summary="Add a service",
        description=(
            "Creates a service for a business owned by the "
            "authenticated vendor."
        ),
        request=ServiceSerializer,
        responses={201: ServiceSerializer},
    ),
)
class ServiceCreateView(generics.ListCreateAPIView):
    """List or create services for the authenticated vendor."""

    serializer_class = ServiceSerializer
    permission_classes = (IsAuthenticated, IsVendor)

    def get_queryset(self):
        return Service.objects.select_related("business").filter(
            business__vendor=self.request.user,
            is_active=True,
        )


@extend_schema(
    tags=["services"],
    summary="Browse available pet services",
    description=(
        "Public listing of active services offered by active, approved "
        "businesses. A service's category must be active, customer-visible, "
        "and approved for that business. The image uses the service image "
        "when present, otherwise the business logo; it is null if neither "
        "exists. Availability is based on availability_status, not weekly "
        "availability slots."
    ),
    parameters=[
        OpenApiParameter(
            "search",
            str,
            description="Case-insensitive match in service name or description.",
        ),
        OpenApiParameter("category", int, description="Service category ID."),
        OpenApiParameter(
            "city_district",
            str,
            description="Case-insensitive business city or district match.",
        ),
        OpenApiParameter("min_price", float, description="Minimum service price."),
        OpenApiParameter("max_price", float, description="Maximum service price."),
        OpenApiParameter("page", int, description="Page number, starting at 1."),
        OpenApiParameter(
            "page_size",
            int,
            description="Results per page (default 12, maximum 50).",
        ),
    ],
    responses={200: PublicServiceSerializer(many=True)},
)
class PublicServiceListView(generics.ListAPIView):
    serializer_class = PublicServiceSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    pagination_class = PublicServicePagination

    def get_queryset(self):
        return filter_public_services(
            public_services(),
            self.request.query_params,
        )


@extend_schema_view(
    get=extend_schema(
        tags=["services"],
        summary="View one of my services",
    ),
    put=extend_schema(tags=["services"], summary="Edit a service"),
    patch=extend_schema(tags=["services"], summary="Edit a service"),
    delete=extend_schema(
        tags=["services"],
        summary="Remove a service",
        description=(
            "Removes one of the authenticated vendor's services. The row is "
            "kept with is_active set to false, so it disappears from use "
            "without breaking anything that points at it."
        ),
    ),
)
class ServiceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View, edit or remove one of the authenticated vendor's services."""

    permission_classes = (IsAuthenticated, IsVendor)

    def get_queryset(self):
        # Only the vendor's own, non-removed services. Anyone else's service
        # (or a removed one) behaves as if it does not exist.
        return Service.objects.select_related("business").filter(
            business__vendor=self.request.user,
            is_active=True,
        )

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ServiceUpdateSerializer
        return ServiceSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        
@extend_schema_view(
    get=extend_schema(tags=["services"], summary="List a service's time slots"),
    post=extend_schema(
        tags=["services"],
        summary="Add a time slot",
        description=(
            "Adds a weekly time slot (weekday 0 is Monday) to one of the "
            "authenticated vendor's services. The slot must be at least as "
            "long as the service and can't overlap another slot that day."
        ),
        request=AvailabilitySlotSerializer,
        responses={201: AvailabilitySlotSerializer},
    ),
)
class ServiceSlotListCreateView(generics.ListCreateAPIView):
    """List or add the weekly time slots of one of the vendor's services."""
    serializer_class = AvailabilitySlotSerializer
    permission_classes = (IsAuthenticated, IsVendor)

    def get_service(self, lock=False):
        # Only the vendor's own, non-removed services. Anyone else's service
        # behaves as if it does not exist (404).
        queryset = Service.objects.filter(
            business__vendor=self.request.user,
            is_active=True,
        )
        if lock:
            # Hold a lock on the service row until the request ends, so two
            # simultaneous requests can't both pass the overlap check.
            queryset = queryset.select_for_update(of=("self",))
        return get_object_or_404(queryset, pk=self.kwargs["service_id"])

    def get_queryset(self):
        # drf-spectacular builds the API docs without a real request.
        if getattr(self, "swagger_fake_view", False):
            return AvailabilitySlot.objects.none()
        return self.get_service().availability_slots.all()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        service = self.get_service(lock=True)

        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "service": service},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(service=service)

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
@extend_schema(
    tags=["services"],
    summary="Remove a time slot",
    description=(
        "Deletes one weekly time slot of the authenticated vendor's own "
        "service. Another vendor's slot returns 404."
    ),
)
class ServiceSlotDeleteView(generics.DestroyAPIView):
    """Remove one weekly time slot."""

    serializer_class = AvailabilitySlotSerializer
    permission_classes = (IsAuthenticated, IsVendor)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AvailabilitySlot.objects.none()

        # The slot must belong to the service named in the URL, and that
        # service must be the vendor's own and still active. Otherwise it
        # behaves as if it does not exist.
        return AvailabilitySlot.objects.filter(
            service_id=self.kwargs["service_id"],
            service__business__vendor=self.request.user,
            service__is_active=True,
        )
        
        
@extend_schema(
    tags=["services"],
    summary="Weekly availability calendar for a service",
    description=(
        "Returns all seven days, Monday first, each with its time slots. "
        "Days with no slots return an empty list."
    ),
    responses=ServiceCalendarSerializer,
)
class ServiceAvailabilityCalendarView(generics.GenericAPIView):
    """The vendor's weekly calendar for one of their services."""

    serializer_class = ServiceCalendarSerializer
    permission_classes = (IsAuthenticated, IsVendor)

    def get(self, request, service_id):
        service = get_object_or_404(
            Service.objects.filter(business__vendor=request.user, is_active=True),
            pk=service_id,
        )

        # One query for all slots, then sorted into days in Python.
        # The model's default ordering already puts them in time order.
        slots = list(service.availability_slots.all())

        days = [
            {
                "weekday": weekday.value,
                "day": weekday.label,
                "slots": [slot for slot in slots if slot.weekday == weekday.value],
            }
            for weekday in AvailabilitySlot.Weekday
        ]

        payload = {
            "service_id": service.pk,
            "service_name": service.name,
            "duration": service.duration,
            "availability_status": service.availability_status,
            "days": days,
        }
        return Response(ServiceCalendarSerializer(payload).data)


@extend_schema(
    tags=["services"],
    summary="List services waiting for review (administrators)",
    description="Active services that are neither approved nor rejected, oldest first.",
)
class AdminPendingServiceListView(generics.ListAPIView):
    serializer_class = ServiceSerializer
    permission_classes = (IsAdmin,)
    pagination_class = PublicServicePagination

    def get_queryset(self):
        return (
            Service.objects.pending_review()
            .select_related("business", "category")
            .order_by("created_at")
        )


class AdminServiceReviewBaseView(generics.GenericAPIView):
    serializer_class = ServiceSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return Service.objects.filter(is_active=True).select_related(
            "business__vendor", "category"
        )


@extend_schema(
    tags=["services"],
    summary="Approve a service (administrators)",
    request=None,
    description=(
        "Marks the service as approved and notifies the vendor. Customers "
        "still only see it once its category is approved for the business."
    ),
)
class AdminServiceApproveView(AdminServiceReviewBaseView):
    @transaction.atomic
    def post(self, request, pk):
        service = self.get_object()

        if service.approved:
            raise serializers.ValidationError("This service is already approved.")

        service.approved = True
        service.rejection_reason = ""
        service.reviewed_by = request.user
        service.reviewed_at = timezone.now()
        service.save(
            update_fields=[
                "approved",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        # Notify only if the database change actually committed.
        transaction.on_commit(lambda: notify_listing_approved(service))

        return Response(self.get_serializer(service).data)


@extend_schema(
    tags=["services"],
    summary="Reject a service (administrators)",
    request=ServiceRejectSerializer,
    description=(
        "Hides the service, stores the reason and notifies the vendor. "
        "The vendor can edit the service to send it for review again."
    ),
)
class AdminServiceRejectView(AdminServiceReviewBaseView):
    @transaction.atomic
    def post(self, request, pk):
        service = self.get_object()

        if not service.approved and service.rejection_reason:
            raise serializers.ValidationError("This service is already rejected.")

        data = ServiceRejectSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        service.approved = False
        service.rejection_reason = data.validated_data["reason"]
        service.reviewed_by = request.user
        service.reviewed_at = timezone.now()
        service.save(
            update_fields=[
                "approved",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        transaction.on_commit(lambda: notify_listing_rejected(service))

        return Response(self.get_serializer(service).data)
