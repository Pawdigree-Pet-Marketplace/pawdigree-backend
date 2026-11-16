from django.conf import settings
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from urllib3 import request

from .gateways import GatewayError, get_gateway
from .models import Payment
from .serializers import PaymentSerializer, StartPaymentSerializer
from .services import process_gateway_event, start_payment


class PaymentMethodListView(APIView):
    """The payment methods a customer can choose from."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(
            {
                "methods": list(settings.PAYMENT_METHODS),
                "currency": settings.PAYMENT_CURRENCY,
            }
        )


class StartPaymentView(APIView):
    """Start paying for an order. Returns the link to send the customer to."""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = StartPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = start_payment(
            request.user,
            serializer.validated_data["order_id"],
            serializer.validated_data["method"],
        )
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )


class PaymentStatusView(generics.RetrieveAPIView):
    """The payment for one of the customer's orders. The frontend polls this."""

    serializer_class = PaymentSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = "order_id"

    def get_queryset(self):
        return Payment.objects.select_related("order").filter(
            order__customer=self.request.user
        )


class PaymentWebhookView(APIView):
    """Called by the gateway, not by the frontend."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        gateway = get_gateway()
        try:
            event = gateway.read_webhook(request)
        except GatewayError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            process_gateway_event(event)
        except NotFound:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(gateway.acknowledgement(event), status=status.HTTP_200_OK)
