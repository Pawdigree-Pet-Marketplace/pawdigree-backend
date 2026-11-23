from django.urls import path

from .admin_views import AdminBookingListView, AdminBookingStatusView

urlpatterns = [
    path(
        "bookings/",
        AdminBookingListView.as_view(),
        name="admin-booking-list",
    ),
    path(
        "bookings/<int:booking_id>/status/",
        AdminBookingStatusView.as_view(),
        name="admin-booking-status",
    ),
]
