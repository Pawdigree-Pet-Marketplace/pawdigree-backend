from django.urls import path

from .views import (
    VendorBookingTransactionListView,
    VendorOrderTransactionListView,
    VendorPetSaleTransactionListView,
)

urlpatterns = [
    path("orders/", VendorOrderTransactionListView.as_view(), name="vendor-transactions-orders"),
    path(
        "pet-sales/",
        VendorPetSaleTransactionListView.as_view(),
        name="vendor-transactions-pet-sales",
    ),
    path(
        "bookings/",
        VendorBookingTransactionListView.as_view(),
        name="vendor-transactions-bookings",
    ),
]
