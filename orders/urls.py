from django.urls import path

from .views import CheckoutView, VendorOrderListView, VendorOrderStatusView

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="order-checkout"),
    path("vendor/", VendorOrderListView.as_view(), name="vendor-order-list"),
    path(
        "vendor/<int:pk>/status/",
        VendorOrderStatusView.as_view(),
        name="vendor-order-status",
    ),
]
