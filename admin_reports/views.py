from django.db import transaction
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from accounts.models import User
from audit.services import record
from common.permissions import IsAdmin, IsSystemAdmin

from .exporters import export_response
from .filters import REPORT_FILTERS, ReportFilterSerializer
from .models import SavedReport
from .serializers import (
    SavedReportCreateSerializer,
    SavedReportDetailSerializer,
    SavedReportListSerializer,
    SavedReportTrashSerializer
)
from .services import generate_report, record_export, save_report

TAG = "admin-reports"


def live_docs(report_type, summary):
    filters = ", ".join(sorted(REPORT_FILTERS[report_type]))
    return extend_schema_view(
        get=extend_schema(
            tags=[TAG],
            summary=summary,
            description=(
                f"Computed live. Supported filters: {filters}. "
                "Add export=xlsx or export=pdf to download the same data."
            ),
            parameters=[ReportFilterSerializer],
            responses={200: OpenApiTypes.OBJECT},
        )
    )


class LiveReportView(APIView):
    """Base for the five live reports; subclasses set report_type."""

    permission_classes = (IsAdmin,)
    report_type = None

    def get(self, request):
        report = generate_report(self.report_type, request.query_params)
        fmt = request.query_params.get("export")
        if fmt:  # already validated as xlsx/pdf by the filter serializer
            record_export(request.user, report, fmt)
            f = report["filters"]
            return export_response(
                report, fmt,
                f"{self.report_type}_{f['date_from']}_{f['date_to']}",
            )
        return Response(report)


@live_docs("overview", "Platform overview (admin)")
class OverviewReportView(LiveReportView):
    report_type = "overview"


@live_docs("users", "Users report (admin)")
class UsersReportView(LiveReportView):
    report_type = "users"


@live_docs("pets", "Pets report (admin)")
class PetsReportView(LiveReportView):
    report_type = "pets"


@live_docs("product-sales", "Product sales report (admin)")
class ProductSalesReportView(LiveReportView):
    report_type = "product-sales"


@live_docs("pet-sales", "Pet sales report (admin)")
class PetSalesReportView(LiveReportView):
    report_type = "pet-sales"


class SavedReportPagination(PageNumberPagination):
    page_size = 20


@extend_schema_view(
    get=extend_schema(
        tags=[TAG], summary="List saved reports (admin)",
        responses={200: SavedReportListSerializer(many=True)},
    ),
    post=extend_schema(
        tags=[TAG], summary="Generate and save a report (admin)",
        request=SavedReportCreateSerializer,
        responses={201: SavedReportDetailSerializer},
    ),
)
class SavedReportListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAdmin,)
    pagination_class = SavedReportPagination
    serializer_class = SavedReportListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedReport.objects.none()
        queryset = SavedReport.objects.select_related("generated_by").defer("data")
        report_type = self.request.query_params.get("report_type")
        if report_type:
            if report_type not in SavedReport.ReportType.values:
                raise ValidationError({"report_type": "Not a valid report type."})
            queryset = queryset.filter(report_type=report_type)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = SavedReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = save_report(request.user, **serializer.validated_data)
        return Response(
            SavedReportDetailSerializer(saved).data,
            status=status.HTTP_201_CREATED,
        )


DENIED = (
    "Only the admin who saved this report, or a system admin, can do this."
)


def can_manage(user, report):
    """The creator, or a system admin (who acts above other admins)."""
    return (
        report.generated_by_id == user.id
        or user.role == User.Role.SYSTEM_ADMIN
        or user.is_superuser
    )


@extend_schema_view(
    get=extend_schema(
        tags=[TAG], summary="View or export a saved report (admin)",
        description="Add export=xlsx or export=pdf to download it.",
        responses={200: SavedReportDetailSerializer},
    ),
    delete=extend_schema(
        tags=[TAG],
        summary="Move a saved report to the trash (admin)",
        description="Restorable for 30 days, then permanently deleted.",
    ),
)
class SavedReportDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = (IsAdmin,)
    serializer_class = SavedReportDetailSerializer
    queryset = SavedReport.objects.select_related("generated_by")  # active only

    def retrieve(self, request, *args, **kwargs):
        saved = self.get_object()
        fmt = request.query_params.get("export")
        if fmt:
            if fmt not in ("xlsx", "pdf"):
                raise ValidationError({"export": "Use xlsx or pdf."})
            record_export(request.user, saved.data, fmt, saved=saved)
            return export_response(
                saved.data, fmt, slugify(saved.name) or f"report-{saved.pk}"
            )
        return Response(self.get_serializer(saved).data)

    def perform_destroy(self, instance):
        user = self.request.user
        if not can_manage(user, instance):
            raise PermissionDenied(DENIED)
        with transaction.atomic():
            instance.soft_delete(user)
            record(
                actor=user,
                action="report.deleted",
                target=instance,
                details={
                    "name": instance.name,
                    "report_type": instance.report_type,
                    "filters": instance.filters,
                    "saved_by": (
                        instance.generated_by.email
                        if instance.generated_by else ""
                    ),
                    "saved_at": instance.created_at.isoformat(),
                    "restorable_until": instance.restorable_until.isoformat(),
                    "deleted_by_system_admin": (
                        instance.generated_by_id != user.id
                    ),
                },
            )


@extend_schema(
    tags=[TAG],
    summary="List deleted reports that can still be restored (admin)",
    responses={200: SavedReportTrashSerializer(many=True)},
)
class SavedReportTrashListView(generics.ListAPIView):
    permission_classes = (IsAdmin,)
    pagination_class = SavedReportPagination
    serializer_class = SavedReportTrashSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedReport.all_objects.none()
        return (
            SavedReport.all_objects.restorable()
            .select_related("generated_by", "deleted_by")
            .defer("data")
            .order_by("-deleted_at")
        )


class SavedReportRestoreView(APIView):
    permission_classes = (IsAdmin,)

    @extend_schema(
        tags=[TAG],
        summary="Restore a deleted saved report (admin)",
        description="Only works within 30 days of deletion.",
        request=None,
        responses={200: SavedReportListSerializer},
    )
    def post(self, request, pk):
        # restorable() already excludes anything past the 30-day window.
        report = get_object_or_404(
            SavedReport.all_objects.restorable()
            .select_related("generated_by")
            .defer("data"),
            pk=pk,
        )
        if not can_manage(request.user, report):
            raise PermissionDenied(DENIED)
        with transaction.atomic():
            report.restore()
            record(
                actor=request.user,
                action="report.restored",
                target=report,
                details={"name": report.name, "report_type": report.report_type},
            )
        return Response(SavedReportListSerializer(report).data)