
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsAdmin, IsCustomer, IsVendor

from .models import AdoptionApplication
from .serializers import (
    AdoptionApplicationCreateSerializer,
    AdoptionApplicationSerializer,
    AdoptionDecisionResponseSerializer,
    AdoptionDecisionUpdateSerializer,
    VendorAdoptionApplicationSerializer,
    InfoMessageInputSerializer,
)
from .services import (
    create_adoption_application,
    decide_adoption_application,
    request_adoption_info,
)


@extend_schema(
    summary="Submit an adoption application",
    description=(
        "A customer applies to adopt or buy a pet. The pet must be "
        "approved and available, and the customer can have only one open "
        "application per pet."
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
        pet_id = data.pop("pet")

        application = create_adoption_application(request.user, pet_id, data)
        return Response(
            AdoptionApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Approve or reject an adoption application",
    request=AdoptionDecisionUpdateSerializer,
    responses={200: AdoptionDecisionResponseSerializer},
)
class AdoptionApplicationDecisionView(generics.GenericAPIView):
    serializer_class = AdoptionDecisionUpdateSerializer
    permission_classes = (IsAuthenticated, IsVendor | IsAdmin)

    def patch(self, request, application_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        application = decide_adoption_application(
            application_id=application_id,
            actor=request.user,
            decision=serializer.validated_data["status"],
            decision_reason=serializer.validated_data.get(
                "decision_reason", ""
            ),
        )

        return Response(
            AdoptionDecisionResponseSerializer(application).data,
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="List the current customer's adoption applications",
    description=(
        "Returns adoption applications belonging to the authenticated "
        "customer, including each application's current status."
    ),
    responses={200: AdoptionApplicationSerializer(many=True)},
)
class CustomerAdoptionStatusView(generics.ListAPIView):
    serializer_class = AdoptionApplicationSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def get_queryset(self):
        return (
            AdoptionApplication.objects
            .filter(customer=self.request.user)
            .select_related("pet")
            .prefetch_related("info_messages")
            .order_by("-created_at")
        )


@extend_schema(
    summary="List adoption applications for vendor pets",
    responses={200: VendorAdoptionApplicationSerializer(many=True)},
)
class VendorAdoptionApplicationListView(generics.ListAPIView):
    serializer_class = VendorAdoptionApplicationSerializer
    permission_classes = (IsAuthenticated, IsVendor | IsAdmin)

    def get_queryset(self):
        user = self.request.user
        queryset = AdoptionApplication.objects.all()

        if not IsAdmin().has_permission(self.request, self):
            queryset = queryset.filter(
                pet__vendor=user,
                pet__business__vendor=user,
            )

        queryset = (
            queryset
            .select_related("pet", "customer", "pet__business")
            .prefetch_related("info_messages")
            .order_by("-created_at")
        )

        pet_id = self.request.query_params.get("pet_id")
        if pet_id is not None:
            try:
                pet_id = int(pet_id)
            except (TypeError, ValueError):
                raise serializers.ValidationError({
                    "pet_id": "Must be a valid integer."
                })

            queryset = queryset.filter(pet_id=pet_id)

        return queryset
    
    
@extend_schema(
    summary="Request more information from an applicant",
    description=(
        "The vendor who owns the pet asks the applicant a question. The "
        "application moves to INFO_REQUESTED until the applicant replies. "
        "Only a pending application can be asked."
    ),
    request=InfoMessageInputSerializer,
    responses={201: VendorAdoptionApplicationSerializer},
)
class AdoptionInfoRequestView(generics.GenericAPIView):
    serializer_class = InfoMessageInputSerializer
    # Role check at the door. Ownership is checked inside the service.
    permission_classes = (IsAuthenticated, IsVendor)

    def post(self, request, application_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        application = request_adoption_info(
            application_id=application_id,
            actor=request.user,
            message=serializer.validated_data['message'],
        )

        return Response(
            VendorAdoptionApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )
