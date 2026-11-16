from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

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
)
from .services import cancel_booking, create_booking, reschedule_booking


@extend_schema(
    tags=["bookings"],
    summary="List my bookings",
    description=(
        "Returns bookings for services owned by the authenticated vendor, "
        "newest first, including customer identification and booking details."
    ),
    responses={200: VendorBookingSerializer(many=True)},
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

