from django.urls import path

from .views import (
    BusinessDetailView,
    BusinessListCreateView,
    BusinessVerificationStatusView,
)

urlpatterns = [
    path("", BusinessListCreateView.as_view(), name="business-list"),
    path(
        "verification-status/",
        BusinessVerificationStatusView.as_view(),
        name="business-verification-status",
    ),
    path("<uuid:pk>/", BusinessDetailView.as_view(), name="business-detail"),
]
