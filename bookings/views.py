from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from common.permissions import IsCustomer, IsVendor
from services.views import public_services

from .availability import free_start_times
from .models import Booking
from .serializers import (
    BookingCreateSerializer,
    BookingRescheduleSerializer,
    BookingSerializer,
    FreeTimesQuerySerializer,
    FreeTimesSerializer,
    VendorBookingSerializer,
    VendorBookingStatusSerializer,
)
from .services import (
    cancel_booking,
    change_booking_status,
    create_booking,
    reschedule_booking,
)


@extend_schema(
    tags=["bookings"],
    summary="List my bookings",
    description=(
        "Requires an authenticated vendor. Returns all bookings for services "
        "whose business belongs to that vendor, newest first, including "
        "customer identification and booking details. No other vendor's "
        "bookings are returned."
    ),
    responses={
        200: VendorBookingSerializer(many=True),
        401: OpenApiResponse(description="Authentication is required."),
        403: OpenApiResponse(
            description="Only vendor accounts may use this endpoint."
        ),
    },
)
class VendorBookingListView(generics.ListAPIView):
    """List all bookings for services owned by the authenticated vendor."""

    serializer_class = VendorBookingSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()

        return (
            Booking.objects.filter(service__business__vendor=self.request.user)
            .select_related("customer", "service", "service__business")
            .order_by("-created_at", "-booking_id")
        )


@extend_schema(
    tags=["bookings"],
    summary="Update the status of my booking",
    description=(
        "Requires an authenticated vendor and only updates bookings for "
        "services whose business belongs to that vendor. A pending booking "
        "can be accepted or declined; declining requires a non-empty "
        "decision_reason. An accepted booking can be completed when the "
        "current time is at or after end_at. Declined, completed and "
        "cancelled bookings are terminal. Other transitions are refused."
    ),
    request=VendorBookingStatusSerializer,
    responses={
        200: VendorBookingSerializer,
        400: OpenApiResponse(
            description=(
                "The status or decline reason is invalid, the transition is "
                "not allowed, or the booking has not ended."
            )
        ),
        401: OpenApiResponse(description="Authentication is required."),
        403: OpenApiResponse(
            description="Only vendor accounts may use this endpoint."
        ),
        404: OpenApiResponse(
            description="The booking was not found for this vendor."
        ),
    },
)
class VendorBookingStatusView(generics.GenericAPIView):
    """Apply an allowed status transition to one of the vendor's bookings."""

    serializer_class = VendorBookingStatusSerializer
    permission_classes = (IsVendor,)

    def patch(self, request, booking_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = change_booking_status(
            request.user,
            booking_id,
            serializer.validated_data["status"],
            serializer.validated_data.get("decision_reason", ""),
        )
        return Response(VendorBookingSerializer(booking).data)


@extend_schema(
    tags=["bookings"],
    summary="Free start times for a service on a date",
    description=(
        "Returns the start times a customer can book for one service on one "
        "date (Africa/Kampala time). Times in the past and times already held "
        "by a pending or accepted booking are left out."
    ),
    parameters=[
        OpenApiParameter(
            "date", str, required=True, description="Date as YYYY-MM-DD."
        )
    ],
    responses=FreeTimesSerializer,
)
class ServiceFreeTimesView(generics.GenericAPIView):
    """Bookable start times for one service on one date."""

    serializer_class = FreeTimesSerializer
    permission_classes = (AllowAny,)

    def get(self, request, service_id):
        service = get_object_or_404(public_services(), pk=service_id)

        query = FreeTimesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        day = query.validated_data["date"]

        payload = {
            "service_id": service.pk,
            "date": day,
            "duration": service.duration,
            "times": [start.isoformat() for start in free_start_times(service, day)],
        }
        return Response(FreeTimesSerializer(payload).data)

@extend_schema(
    tags=["bookings"],
    summary="Book a service",
    description=(
        "Books one free start time of a service for the authenticated "
        "customer. The booking starts as pending. start_at must be one of "
        "the times returned by the service's times endpoint."
    ),
    request=BookingCreateSerializer,
    responses={201: BookingSerializer},
)
class BookingCreateView(generics.GenericAPIView):
    """A customer books a service at a free time."""

    serializer_class = BookingCreateSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = create_booking(request.user, **serializer.validated_data)
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["bookings"],
    summary="Cancel my booking",
    description=(
        "Cancels one of the authenticated customer's own pending or "
        "accepted bookings that hasn't started yet. The time becomes "
        "free for other customers. Someone else's booking returns 404."
    ),
    request=None,
    responses={200: BookingSerializer},
)
class BookingCancelView(generics.GenericAPIView):
    """A customer cancels their own booking."""

    serializer_class = BookingSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def post(self, request, booking_id):
        booking = cancel_booking(request.user, booking_id)
        return Response(BookingSerializer(booking).data)


@extend_schema(
    tags=["bookings"],
    summary="Reschedule my booking",
    description=(
        "Moves one of the authenticated customer's own pending or accepted "
        "bookings to another free time. start_at must be one of the times "
        "returned by the service's times endpoint. The booking goes back "
        "to pending so the vendor can approve the new time."
    ),
    request=BookingRescheduleSerializer,
    responses={200: BookingSerializer},
)
class BookingRescheduleView(generics.GenericAPIView):
    """A customer moves their own booking to another free time."""

    serializer_class = BookingRescheduleSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def post(self, request, booking_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = reschedule_booking(
            request.user, booking_id, serializer.validated_data["start_at"]
        )
        return Response(BookingSerializer(booking).data)
    
    
@extend_schema(
    tags=["bookings"],
    summary="List my bookings",
    description=(
        "Returns the authenticated customer's own bookings, newest first, "
        "with the service, time, current status and, for declined bookings, "
        "the vendor's reason. Other customers' bookings are never returned. "
        "Optional: status=pending|accepted|declined|completed|cancelled."
    ),
    parameters=[
        OpenApiParameter(
            "status",
            str,
            description="Only show bookings with this status, e.g. accepted.",
        )
    ],
    responses={
        200: BookingSerializer(many=True),
        401: OpenApiResponse(description="Authentication is required."),
        403: OpenApiResponse(description="Only customer accounts may use this endpoint."),
    },
)
class CustomerBookingListView(generics.ListAPIView):
    """List the authenticated customer's own bookings."""

    serializer_class = BookingSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()

        queryset = (
            Booking.objects.filter(customer=self.request.user)
            .select_related("service")
            .order_by("-created_at", "-booking_id")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in Booking.Status.values:
                raise ValidationError({"status": "Not a valid booking status."})
            queryset = queryset.filter(status=status_filter)
        return queryset

