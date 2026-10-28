from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsVendor

from .models import Service
from .serializers import ServiceSerializer


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
