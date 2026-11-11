from django.db import models

from common.models import TimeStampedModel
from orders.models import Order


class Payment(TimeStampedModel):
    """The single payment made for one order."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        REFUND_REQUIRED = "REFUND_REQUIRED", "Refund required"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="payment",
    )
    method = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    gateway_reference = models.CharField(max_length=100, unique=True)
    gateway_transaction_id = models.CharField(max_length=100, blank=True)
    payment_url = models.URLField(max_length=500, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    gateway_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment {self.gateway_reference} ({self.status})"
