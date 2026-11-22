"""Read-only administrator dashboard API views."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsAdmin

from .services import get_dashboard_statistics, get_dashboard_summary


@extend_schema(
    summary="Get administrator dashboard summary",
    description=(
        "Returns the overview metrics for users, vendors, businesses, "
        "listings, bookings, orders and reports. Requires an authenticated "
        "ADMIN or SYSTEM_ADMIN role (or a superuser)."
    ),
    responses={200: OpenApiTypes.OBJECT},
)
class AdminDashboardSummaryView(APIView):
    """Return high-level dashboard metrics."""

    permission_classes = (IsAuthenticated, IsAdmin)

    def get(self, request, *args, **kwargs):
        return Response(get_dashboard_summary())


@extend_schema(
    summary="Get administrator dashboard statistics",
    description=(
        "Returns detailed breakdowns by user role and account status, "
        "business verification and active state, listing type and review "
        "state, booking status, order status, and report status and reason. "
        "Requires an authenticated ADMIN or SYSTEM_ADMIN role (or a "
        "superuser)."
    ),
    responses={200: OpenApiTypes.OBJECT},
)
class AdminDashboardStatisticsView(APIView):
    """Return dashboard chart and table breakdowns."""

    permission_classes = (IsAuthenticated, IsAdmin)

    def get(self, request, *args, **kwargs):
        return Response(get_dashboard_statistics())
