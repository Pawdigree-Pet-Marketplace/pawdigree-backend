
from django.urls import path

from .views import (
    AdoptionApplicationCreateView,
    AdoptionApplicationDecisionView,
    AdoptionInfoRequestView,
    CustomerAdoptionStatusView,
    VendorAdoptionApplicationListView,
    
)

urlpatterns = [
    path(
        "applications/",
        AdoptionApplicationCreateView.as_view(),
        name="adoption-application-create",
    ),
    path(
        "applications/vendor/",
        VendorAdoptionApplicationListView.as_view(),
        name="vendor-adoption-application-list",
    ),
    path(
        "applications/<uuid:application_id>/decision/",
        AdoptionApplicationDecisionView.as_view(),
        name="adoption-application-decision",
    ),
    path(
        "my-applications/",
        CustomerAdoptionStatusView.as_view(),
        name="customer-adoption-status",
    ),
    path("<uuid:application_id>/request-info/", AdoptionInfoRequestView.as_view(), name="adoption-request-info",),
]
