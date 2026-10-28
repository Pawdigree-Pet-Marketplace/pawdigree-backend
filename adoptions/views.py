from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsCustomer

from .serializers import (
    AdoptionApplicationCreateSerializer,
    AdoptionApplicationSerializer,
)
from .services import create_adoption_application


@extend_schema(
    summary='Submit an adoption application',
    description=(
        'A customer applies to adopt or buy a pet. The pet must be '
        'approved and available, and the customer can have only one open '
        'application per pet.'
    ),
    responses={201: AdoptionApplicationSerializer},
)
class AdoptionApplicationCreateView(generics.GenericAPIView):
    serializer_class = AdoptionApplicationCreateSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        pet_id = data.pop('pet')

        application = create_adoption_application(request.user, pet_id, data)
        return Response(
            AdoptionApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )