from django.urls import path

from .views import (
    PublicServiceListView,
    ServiceAvailabilityCalendarView,
    ServiceCreateView,
    ServiceDetailView,
    ServiceSlotDeleteView,
    ServiceSlotListCreateView,
)

urlpatterns = [
    path("", ServiceCreateView.as_view(), name="service-create"),
    path("public/", PublicServiceListView.as_view(), name="service-public-list"),
    path("<int:pk>/", ServiceDetailView.as_view(), name="service-detail"),
    path("<int:service_id>/slots/",  ServiceSlotListCreateView.as_view(), name="service-slot-list",),
    path("<int:service_id>/slots/<int:pk>/", ServiceSlotDeleteView.as_view(), name="service-slot-detail",),
    path("<int:service_id>/availability/", ServiceAvailabilityCalendarView.as_view(), name="service-availability",),
]
