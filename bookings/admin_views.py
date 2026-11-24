from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsAdmin

from .filters import filter_admin_bookings
from .models import Booking
from .serializers import AdminBookingSerializer, AdminBookingStatusSerializer
from .services import admin_change_booking_status


class AdminBookingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


@extend_schema(
    tags=["admin-bookings"],
    summary="List all platform bookings",
    description=(
        "ADMIN and SYSTEM_ADMIN only. Returns every booking on the platform "
        "across all customers, vendors and businesses, newest first. "
        "All filters are optional and combined with AND behaviour."
    ),
    parameters=[
        OpenApiParameter(
            "status",
            str,
            enum=Booking.Status.values,
            description="Only bookings with this status.",
        ),
        OpenApiParameter(
            "date_from",
            str,
            description="Only bookings starting on or after this date (YYYY-MM-DD).",
        ),
        OpenApiParameter(
            "date_to",
            str,
            description="Only bookings starting on or before this date (YYYY-MM-DD).",
        ),
        OpenApiParameter(
            "customer",
            str,
            description=(
                "A numeric customer id, or a partial username/first name/last name "
                "(case-insensitive)."
            ),
        ),
        OpenApiParameter(
            "business",
            str,
            description="A business UUID. Returns bookings for services in that business.",
        ),
        OpenApiParameter("page", int, description="Page number, starting at 1."),
        OpenApiParameter(
            "page_size",
            int,
            description="Results per page (default 20, maximum 50).",
        ),
    ],
    responses={
        200: AdminBookingSerializer(many=True),
        400: OpenApiResponse(description="Invalid filter value."),
        401: OpenApiResponse(description="Authentication is required."),
        403: OpenApiResponse(description="Only administrators may use this endpoint."),
    },
)
class AdminBookingListView(generics.ListAPIView):
    serializer_class = AdminBookingSerializer
    permission_classes = (IsAuthenticated, IsAdmin)
    pagination_class = AdminBookingPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        queryset = Booking.objects.select_related(
            "customer",
            "service",
            "service__business",
            "service__business__vendor",
        ).order_by("-created_at", "-booking_id")
        return filter_admin_bookings(queryset, self.request.query_params)


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
