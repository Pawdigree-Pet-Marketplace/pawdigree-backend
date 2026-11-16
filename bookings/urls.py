from django.urls import path

from .views import (
    BookingCancelView,
    BookingCreateView,
    BookingRescheduleView,
    ServiceFreeTimesView,
    VendorBookingListView,
)

urlpatterns = [
    path("vendor/", VendorBookingListView.as_view(), name="booking-vendor-list"),
    path("services/<int:service_id>/times/",ServiceFreeTimesView.as_view(),name="booking-service-times",),
    path("", BookingCreateView.as_view(), name="booking-create"),
    path("<int:booking_id>/cancel/", BookingCancelView.as_view(), name="booking-cancel"),
    path("<int:booking_id>/reschedule/",BookingRescheduleView.as_view(),name="booking-reschedule",),
]
