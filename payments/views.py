from django.conf import settings
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gateways import GatewayError, GatewayEvent, get_gateway
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
        try:
            event = get_gateway().read_webhook(request)
        except GatewayError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            process_gateway_event(event)
        except NotFound:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_200_OK)


class SandboxPaymentSimulationSerializer(serializers.Serializer):
    """Validate a simulated sandbox payment result."""

    reference = serializers.CharField(max_length=100)
    result = serializers.ChoiceField(choices=("success", "failed"))


class SandboxPaymentSimulationView(APIView):
    """Simulate a sandbox result for the customer who owns the payment.

    Development only. This never moves real money.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        if (
            not settings.DEBUG
            or settings.PAYMENT_GATEWAY_CLASS
            != "payments.gateways.sandbox.SandboxGateway"
        ):
            raise NotFound()

        if getattr(request.user, "role", None) != "CUSTOMER":
            raise PermissionDenied("Only customers can simulate their payments.")

        serializer = SandboxPaymentSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = Payment.objects.select_related("order").filter(
            gateway_reference=serializer.validated_data["reference"],
            order__customer=request.user,
        ).first()

        if payment is None:
            raise NotFound("Payment not found.")

        if payment.status != Payment.Status.PENDING:
            raise ValidationError(
                {"payment": "This payment has already been processed."}
            )

        succeeded = serializer.validated_data["result"] == "success"

        event = GatewayEvent(
            reference=payment.gateway_reference,
            transaction_id=payment.gateway_transaction_id,
            succeeded=succeeded,
            amount=payment.amount,
            currency=payment.currency,
            payload={
                "reference": payment.gateway_reference,
                "status": serializer.validated_data["result"],
                "simulated": True,
            },
            failure_reason="" if succeeded else "Simulated sandbox failure.",
        )

        payment = process_gateway_event(event)

        return Response(PaymentSerializer(payment).data)
