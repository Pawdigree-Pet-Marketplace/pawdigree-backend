from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from common.permissions import IsAdmin

from .admin_serializers import (
    AdminReportSerializer,
    RemoveItemSerializer,
    ReportStatusSerializer,
)
from .models import Report
from .moderation import close_report, remove_reported_item


class AdminReportPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _reports():
    return Report.objects.select_related("reporter", "reviewed_by")


@extend_schema(
    tags=["reports"],
    summary="Report queue (administrators)",
    description=(
        "Pending reports by default, oldest first. Use status to see handled "
        "reports (newest first)."
    ),
    parameters=[
        OpenApiParameter("status", str, description="PENDING (default), DISMISSED or RESOLVED."),
        OpenApiParameter(
            "reported_item_type", str, description="PET, PRODUCT, SERVICE, REVIEW or GENERAL."
        ),
    ],
)
class AdminReportListView(generics.ListAPIView):
    serializer_class = AdminReportSerializer
    permission_classes = (IsAdmin,)
    pagination_class = AdminReportPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Report.objects.none()

        params = self.request.query_params
        status_value = (params.get("status") or Report.Status.PENDING.value).upper()
        if status_value not in Report.Status.values:
            raise ValidationError({"status": "Not a valid status."})
        queryset = _reports().filter(status=status_value)

        item_type = params.get("reported_item_type")
        if item_type:
            item_type = item_type.upper()
            if item_type not in Report.ReportedItemType.values:
                raise ValidationError({"reported_item_type": "Not a valid item type."})
            queryset = queryset.filter(reported_item_type=item_type)

        if status_value == Report.Status.PENDING:
            return queryset.order_by("created_at", "id")
        return queryset.order_by("-reviewed_at", "-id")


@extend_schema(tags=["reports"], summary="One report (administrators)")
class AdminReportDetailView(generics.RetrieveAPIView):
    serializer_class = AdminReportSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return _reports()


@extend_schema(
    tags=["reports"],
    summary="Dismiss a report (administrators)",
    description=(
        "DISMISSED closes a report with no action. RESOLVED is accepted only "
        "for general reports; a report about an item is resolved by removing "
        "the item. Only a PENDING report can be changed."
    ),
    request=ReportStatusSerializer,
    responses={200: AdminReportSerializer},
)
class AdminReportStatusView(generics.GenericAPIView):
    serializer_class = ReportStatusSerializer
    permission_classes = (IsAdmin,)

    def patch(self, request, pk):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        report = close_report(
            pk,
            request.user,
            data.validated_data["status"],
            data.validated_data["note"],
        )
        return Response(AdminReportSerializer(report).data)


@extend_schema(
    tags=["reports"],
    summary="Remove the reported item (administrators)",
    description=(
        "Hides the reported review, or rejects the reported listing (the "
        "vendor is notified and can edit and resubmit), and resolves the "
        "report together with other pending reports about the same item. "
        "Nothing is deleted. The reason is required."
    ),
    request=RemoveItemSerializer,
    responses={200: AdminReportSerializer},
)
class AdminReportRemoveView(generics.GenericAPIView):
    serializer_class = RemoveItemSerializer
    permission_classes = (IsAdmin,)

    def post(self, request, pk):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        report = remove_reported_item(pk, request.user, data.validated_data["reason"])
        return Response(AdminReportSerializer(report).data)
