
from django.urls import path

from .views import (
    CheckoutView,
    CustomerOrderDetailView,
    CustomerOrderListView,
    VendorOrderListView,
    VendorOrderStatusView,
)

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="order-checkout"),
    path("my-orders/", CustomerOrderListView.as_view(), name="customer-order-list"),
    path(
        "my-orders/<int:pk>/",
        CustomerOrderDetailView.as_view(),
        name="customer-order-detail",
    ),
    path("vendor/", VendorOrderListView.as_view(), name="vendor-order-list"),
    path(
        "vendor/<int:pk>/status/",
        VendorOrderStatusView.as_view(),
        name="vendor-order-status",
    ),
]
