from django.urls import path

from .views import (
    BusinessDetailView,
    BusinessListCreateView,
    BusinessVerificationStatusView,
    PublicBusinessListView,
    VendorBusinessResponseView,
)

urlpatterns = [
    path("", BusinessListCreateView.as_view(), name="business-list"),
    path(
        "public/",
        PublicBusinessListView.as_view(),
        name="business-public-list",
    ),
    path(
        "verification-status/",
        BusinessVerificationStatusView.as_view(),
        name="business-verification-status",
    ),
    path(
        "<uuid:pk>/response/",
        VendorBusinessResponseView.as_view(),
        name="business-vendor-response",
    ),
    path("<uuid:pk>/", BusinessDetailView.as_view(), name="business-detail"),
]
