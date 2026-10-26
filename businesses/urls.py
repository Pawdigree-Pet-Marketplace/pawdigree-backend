from django.urls import path

from .views import (
    BusinessCategoryRequestView,
    BusinessDetailView,
    BusinessListCreateView,
    BusinessVerificationStatusView,
    PublicBusinessListView,
    VendorBusinessResponseView,
    AdminBusinessDecisionView,
    AdminBusinessDecisionHistoryView
    
)

urlpatterns = [
    path("", BusinessListCreateView.as_view(), name="business-list"),
    path("public/", PublicBusinessListView.as_view(), name="business-public-list",),
    path("verification-status/", BusinessVerificationStatusView.as_view(), name="business-verification-status",),
    path("<uuid:pk>/response/", VendorBusinessResponseView.as_view(), name="business-vendor-response",),
    path("<uuid:business_id>/category-requests/", BusinessCategoryRequestView.as_view(), name="business-category-requests",),
    path("<uuid:pk>/", BusinessDetailView.as_view(), name="business-detail"),
    path("admin/<uuid:pk>/decision/", AdminBusinessDecisionView.as_view(), name="business-admin-decision",),
    path("admin/<uuid:pk>/decisions/", AdminBusinessDecisionHistoryView.as_view(), name="business-admin-decisions",),
]
