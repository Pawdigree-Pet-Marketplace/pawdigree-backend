from django.conf import settings
from django.urls import path

from .views import (
    PaymentMethodListView,
    PaymentStatusView,
    PaymentWebhookView,
    StartPaymentView,
    SandboxPaymentSimulationView,
)

urlpatterns = [
    path("methods/", PaymentMethodListView.as_view(), name="payment-methods"),
    path("start/", StartPaymentView.as_view(), name="payment-start"),
    path("orders/<int:order_id>/", PaymentStatusView.as_view(), name="payment-status"),
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
]

# Never register the simulation endpoint in production.
if (
    settings.DEBUG
    and settings.PAYMENT_GATEWAY_CLASS
    == "payments.gateways.sandbox.SandboxGateway"
):
    urlpatterns.append(
        path(
            "sandbox/simulate/",
            SandboxPaymentSimulationView.as_view(),
            name="sandbox-payment-simulate",
        )
    )
