from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsAdmin

from .models import Booking
from .serializers import AdminBookingSerializer, AdminBookingStatusSerializer
from .services import admin_change_booking_status


@extend_schema(
    tags=["admin-bookings"],
    summary="List all platform bookings",
    description=(
        "ADMIN and SYSTEM_ADMIN only. Returns every booking on the platform "
        "across all customers, vendors and businesses, newest first."
    ),
    responses={
        200: AdminBookingSerializer(many=True),
        401: OpenApiResponse(description="Authentication is required."),
        403: OpenApiResponse(description="Only administrators may use this endpoint."),
    },
)
class AdminBookingListView(generics.ListAPIView):
    serializer_class = AdminBookingSerializer
    permission_classes = (IsAuthenticated, IsAdmin)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        queryset = Booking.objects.select_related(
            "customer",
            "service",
            "service__business",
            "service__business__vendor",
        ).order_by("-created_at", "-booking_id")
        return queryset


@extend_schema(
    tags=["admin-bookings"],
    summary="Update a booking status (administrator)",
    description=(
        "ADMIN and SYSTEM_ADMIN only. Applies an approved administrative "
        "status transition to any platform booking. Declining requires a "
        "non-empty reason. Cancelling requires a non-empty reason. "
        "Completing requires the booking to have ended."
    ),
    request=AdminBookingStatusSerializer,
    responses={
        200: AdminBookingSerializer,
        400: OpenApiResponse(description="Invalid transition or missing reason."),
        401: OpenApiResponse(description="Authentication is required."),
        403: OpenApiResponse(description="Only administrators may use this endpoint."),
        404: OpenApiResponse(description="Booking not found."),
    },
)
class AdminBookingStatusView(generics.GenericAPIView):
    serializer_class = AdminBookingStatusSerializer
    permission_classes = (IsAuthenticated, IsAdmin)

    def patch(self, request, booking_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        admin_change_booking_status(
            administrator=request.user,
            booking_id=booking_id,
            new_status=serializer.validated_data["status"],
            reason=serializer.validated_data.get("reason", ""),
        )
        booking = (
            Booking.objects.select_related(
                "customer",
                "service",
                "service__business",
                "service__business__vendor",
            )
            .get(pk=booking_id)
        )
        return Response(
            AdminBookingSerializer(booking).data, status=status.HTTP_200_OK
        )
