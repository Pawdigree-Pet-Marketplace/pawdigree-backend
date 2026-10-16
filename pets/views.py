from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from common.permissions import IsVendor

from .models import Pet
from .serializers import PetSerializer


@extend_schema(
    tags=["pets"],
    summary="List or create pet listings",
    description=(
        "Allows authenticated vendors to view their own pet listings "
        "and create new listings for businesses they own."
    ),
)
class PetListCreateView(generics.ListCreateAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        return Pet.objects.filter(
            vendor=self.request.user,
        ).select_related("business", "vendor")

    def perform_create(self, serializer):
        serializer.save(vendor=self.request.user)
