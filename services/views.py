from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.response import Response

from common.permissions import IsVendor

from .models import Service, AvailabilitySlot
from .serializers import (
    AvailabilitySlotSerializer,
    ServiceSerializer,
    ServiceUpdateSerializer,
)


@extend_schema(
    tags=["services"],
    summary="Add a service",
    description=(
        "Creates a service for a business owned by the "
        "authenticated vendor."
    ),
    request=ServiceSerializer,
    responses={201: ServiceSerializer},
)
class ServiceCreateView(generics.CreateAPIView):
    """Create a service for the authenticated vendor's business."""

    queryset = Service.objects.select_related("business")
    serializer_class = ServiceSerializer
    permission_classes = (IsAuthenticated, IsVendor)

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
        response={201: AvailabilitySlotSerializer},
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