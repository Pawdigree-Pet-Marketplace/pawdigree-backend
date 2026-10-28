from django.urls import path

from .views import (
    AdminBusinessDecisionView,
    AdminBusinessDecisionHistoryView,
    AdminBusinessListView,
    AdminBusinessDetailView,
    BusinessAppealView,
    BusinessCategoryRequestView,
    BusinessDetailView,
    BusinessListCreateView,
    BusinessReapplyView,
    BusinessSubmitView,
    BusinessVerificationStatusView,
    PublicBusinessListView,
    VendorBusinessResponseView,
    BusinessWithdrawView,        
)

urlpatterns = [
    path("", BusinessListCreateView.as_view(), name="business-list"),
    path("public/", PublicBusinessListView.as_view(), name="business-public-list",),
    path("verification-status/", BusinessVerificationStatusView.as_view(), name="business-verification-status",),
    path("<uuid:pk>/response/", VendorBusinessResponseView.as_view(), name="business-vendor-response",),
    path("<uuid:business_id>/category-requests/", BusinessCategoryRequestView.as_view(), name="business-category-requests",),
    path("<uuid:pk>/", BusinessDetailView.as_view(), name="business-detail"),
    path("<uuid:pk>/submit/", BusinessSubmitView.as_view(),  name="business-submit",),
    path("admin/", AdminBusinessListView.as_view(), name="business-admin-list"),
    path("admin/<uuid:pk>/", AdminBusinessDetailView.as_view(), name="business-admin-detail",),
    path("admin/<uuid:pk>/decision/", AdminBusinessDecisionView.as_view(), name="business-admin-decision",),
    path("admin/<uuid:pk>/decisions/", AdminBusinessDecisionHistoryView.as_view(), name="business-admin-decisions",),
    path("<uuid:pk>/withdraw/", BusinessWithdrawView.as_view(), name="business-withdraw",),
    path("<uuid:pk>/appeal/", BusinessAppealView.as_view(), name="business-appeal",),
    path("<uuid:pk>/reapply/", BusinessReapplyView.as_view(), name="business-reapply",),
]
