"""Admin endpoints for payments that were taken but must be paid back."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from common.permissions import IsAdmin

from .models import Payment
from .refund_serializers import AdminRefundPaymentSerializer, MarkRefundedSerializer
from .refunds import mark_payment_refunded

REFUND_STATUSES = (
    Payment.Status.REFUND_REQUIRED.value,
    Payment.Status.REFUNDED.value,
)


class AdminRefundPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _payments():
    return Payment.objects.select_related(
        "order", "order__customer", "refund", "refund__refunded_by"
    )


@extend_schema(
    tags=["payments"],
    summary="List payments that need a refund (admin)",
    description=(
        "Payments that were taken for an order that could not be completed. "
        "Shows REFUND_REQUIRED by default; use status=REFUNDED to review "
        "refunds already recorded."
    ),
    parameters=[
        OpenApiParameter(
            "status", str, description="REFUND_REQUIRED (default) or REFUNDED."
        ),
    ],
)
class AdminRefundPaymentListView(generics.ListAPIView):
    serializer_class = AdminRefundPaymentSerializer
    permission_classes = (IsAdmin,)
    pagination_class = AdminRefundPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()

        value = self.request.query_params.get("status")
        value = value.upper() if value else Payment.Status.REFUND_REQUIRED.value
        if value not in REFUND_STATUSES:
            raise ValidationError({"status": "Not a valid status."})
        return _payments().filter(status=value).order_by("-created_at", "-id")


class AdminMarkRefundedView(generics.GenericAPIView):
    serializer_class = MarkRefundedSerializer
    permission_classes = (IsAdmin,)

    @extend_schema(
        tags=["payments"],
        summary="Record a refund (admin)",
        description=(
            "Records that the money was paid back to the customer from the "
            "gateway's dashboard and marks the payment REFUNDED. Only a "
            "REFUND_REQUIRED payment can be recorded, once. The administrator, "
            "time, amount, reason and refund reference are kept, and the "
            "action is recorded in the audit log. This does not send money."
        ),
        request=MarkRefundedSerializer,
        responses={200: AdminRefundPaymentSerializer},
    )
    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = mark_payment_refunded(pk, request.user, **serializer.validated_data)
        payment = _payments().get(pk=refund.payment_id)
        return Response(AdminRefundPaymentSerializer(payment).data)
