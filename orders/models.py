from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


class Order(TimeStampedModel):
    """A customer's checkout, which may contain products from multiple businesses.

    The status here is the payment state of the whole checkout. What the
    vendors do afterwards is tracked on each VendorOrder.
    """

    class Status(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        limit_choices_to={"role": "CUSTOMER"},
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
    )
    items_subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # The end of the payment window. After this time an unpaid order is
    # expired and its stock goes back.
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Shipping and contact details given at checkout. The checkout
    # serializer makes them required.
    shipping_name = models.CharField(max_length=150, blank=True, default="")
    shipping_phone = models.CharField(max_length=20, blank=True, default="")
    shipping_address = models.CharField(max_length=255, blank=True, default="")
    shipping_city_district = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Order #{self.pk} - {self.customer}"


class VendorOrder(TimeStampedModel):
    """A business's independently fulfillable portion of a customer's order."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
        PAID = "PAID", "Paid"
        PROCESSING = "PROCESSING", "Processing"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    class RefundStatus(models.TextChoices):
        NONE = "NONE", "No refund"
        REQUIRED = "REQUIRED", "Refund required"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="vendor_orders",
    )
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.PROTECT,
        related_name="vendor_orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
    )
    refund_status = models.CharField(
        max_length=10,
        choices=RefundStatus.choices,
        default=RefundStatus.NONE,
    )
    refund_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_vendor_orders",
    )
    cancel_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("order", "business"),
                name="unique_order_business",
            ),
        )

    def __str__(self):
        return f"Order #{self.order_id} - {self.business.name}"


class OrderItem(TimeStampedModel):
    """A product and its purchased quantity and price within a vendor order."""

    vendor_order = models.ForeignKey(
        VendorOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        null=True,
        blank=True,
    )
    pet = models.ForeignKey(
        "pets.Pet",
        on_delete=models.PROTECT,
        related_name="order_items",
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        ordering = ("created_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("vendor_order", "product"),
                name="unique_product_per_vendor_order",
            ),
            models.UniqueConstraint(
                fields=("vendor_order", "pet"),
                name="unique_pet_per_vendor_order",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="order_item_quantity_gte_1",
            ),
            models.CheckConstraint(
                condition=(
                    Q(product__isnull=False, pet__isnull=True)
                    | Q(product__isnull=True, pet__isnull=False)
                ),
                name="order_item_product_xor_pet",
            ),
            models.CheckConstraint(
                condition=Q(pet__isnull=True) | Q(quantity=1),
                name="order_item_pet_quantity_is_one",
            ),
        )

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def item_name(self):
        return self.pet.name if self.pet_id else self.product.name

    @property
    def item_type(self):
        return "pet" if self.pet_id else "product"

    def __str__(self):
        return (
            f"{self.item_name} x {self.quantity} "
            f"(Vendor order #{self.vendor_order_id})"
        )