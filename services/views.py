from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsVendor

from .models import Service
from .serializers import ServiceSerializer, ServiceUpdateSerializer


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