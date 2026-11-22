from django.urls import path

from .views import AdminDashboardStatisticsView, AdminDashboardSummaryView

urlpatterns = [
    path(
        'summary/',
        AdminDashboardSummaryView.as_view(),
        name='admin-dashboard-summary',
    ),
    path(
        'statistics/',
        AdminDashboardStatisticsView.as_view(),
        name='admin-dashboard-statistics',
    ),
]
