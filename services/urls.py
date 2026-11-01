from django.urls import path

from .views import ServiceCreateView, ServiceDetailView, ServiceSlotListCreateView, ServiceSlotDeleteView

urlpatterns = [
    path("", ServiceCreateView.as_view(), name="service-create"),
    path("<int:pk>/", ServiceDetailView.as_view(), name="service-detail"),
    path("<int:service_id>/slots/",  ServiceSlotListCreateView.as_view(), name="service-slot-list",),
    path("<int:service_id>/slots/<int:pk>/", ServiceSlotDeleteView.as_view(), name="service-slot-detail",),
]
