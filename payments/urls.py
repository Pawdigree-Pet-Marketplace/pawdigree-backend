from django.urls import path

from .views import (
    PaymentMethodListView,
    PaymentStatusView,
    PaymentWebhookView,
    StartPaymentView,
)

urlpatterns = [
    path("methods/", PaymentMethodListView.as_view(), name="payment-methods"),
    path("start/", StartPaymentView.as_view(), name="payment-start"),
    path("orders/<int:order_id>/", PaymentStatusView.as_view(), name="payment-status"),
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
]