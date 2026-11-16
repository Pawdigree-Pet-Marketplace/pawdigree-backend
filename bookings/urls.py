from django.urls import path

from .views import BookingCreateView, ServiceFreeTimesView

urlpatterns = [
    path("services/<int:service_id>/times/",ServiceFreeTimesView.as_view(),name="booking-service-times",),
    path("", BookingCreateView.as_view(), name="booking-create"),
]