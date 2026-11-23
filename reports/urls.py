from django.urls import path

from .admin_views import (
    AdminReportDetailView,
    AdminReportListView,
    AdminReportRemoveView,
    AdminReportStatusView,
)
from .views import ReportCreateView


urlpatterns = [
    path("", ReportCreateView.as_view(), name="report-create"),
    path("admin/", AdminReportListView.as_view(), name="report-admin-list"),
    path(
        "admin/<int:pk>/",
        AdminReportDetailView.as_view(),
        name="report-admin-detail",
    ),
    path(
        "admin/<int:pk>/status/",
        AdminReportStatusView.as_view(),
        name="report-admin-status",
    ),
    path(
        "admin/<int:pk>/remove/",
        AdminReportRemoveView.as_view(),
        name="report-admin-remove",
    ),
]
