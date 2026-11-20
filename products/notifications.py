import logging

from django.conf import settings
from django.core.mail import send_mail

from notification.models import Notification
from notification.services import create_notification
from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        # Listings
        LISTING_APPROVED = "LISTING_APPROVED", "Listing approved"
        LISTING_REJECTED = "LISTING_REJECTED", "Listing rejected"
        LISTING_PENDING = "LISTING_PENDING", "Listing pending"
        # Orders and payments
        ORDER_PLACED = "ORDER_PLACED", "Order placed"
        PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED", "Payment confirmed"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment failed"
        NEW_ORDER = "NEW_ORDER", "New order"
        NEW_PET_SALE = "NEW_PET_SALE", "New pet sale"
        ORDER_STATUS = "ORDER_STATUS", "Order status updated"
        ORDER_CANCELLED = "ORDER_CANCELLED", "Order cancelled"
        ORDER_EXPIRED = "ORDER_EXPIRED", "Order expired"
        REFUND_REQUIRED = "REFUND_REQUIRED", "Refund required"
        REFUND_CONFIRMED = "REFUND_CONFIRMED", "Refund confirmed"
        # Bookings
        BOOKING_NEW = "BOOKING_NEW", "New booking"
        BOOKING_UPDATED = "BOOKING_UPDATED", "Booking updated"
        BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking cancelled"
        BOOKING_RESCHEDULED = "BOOKING_RESCHEDULED", "Booking rescheduled"
        BOOKING_REMINDER = "BOOKING_REMINDER", "Booking reminder"
        # Adoptions
        ADOPTION_NEW = "ADOPTION_NEW", "New adoption application"
        ADOPTION_REPLY = "ADOPTION_REPLY", "Applicant replied"
        ADOPTION_UPDATE = "ADOPTION_UPDATE", "Adoption application update"
        # Business and reviews
        BUSINESS_VERIFICATION = "BUSINESS_VERIFICATION", "Business verification"
        NEW_REVIEW = "NEW_REVIEW", "New review"
        REVIEW_REPLY = "REVIEW_REPLY", "Review reply"

    notification_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    user_role = models.CharField(max_length=20, editable=False)
    # For vendors: which business this is about. Null for customers, admins
    # and notifications created before this field existed.
    business = models.ForeignKey(
        "businesses.Business",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    message = models.TextField()
    # What the frontend opens when the notification is clicked.
    reference_type = models.CharField(max_length=30, blank=True)
    reference_id = models.CharField(
        max_length=40,
        blank=True,
        help_text="Id of the related record (string: some ids are UUIDs).",
    )
    # Stops the same event notifying the same user twice (webhook retries,
    # re-run jobs). Unique per user, because the user id is added to it.
    event_key = models.CharField(
        max_length=120, unique=True, null=True, blank=True, default=None,
        editable=False,
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["user", "business", "is_read"]),
        ]

    def save(self, *args, **kwargs):
        # Snapshot the role when the notification is created.
        if not self.user_role:
            self.user_role = self.user.role
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.type} -> {self.user}"
logger = logging.getLogger(__name__)


def _notify(product, notification_type, message, email_subject):
    vendor = product.business.vendor

    try:
        create_notification(
            user=vendor,
            notification_type=notification_type,
            message=message,
            reference_id=product.pk,
        )
    except Exception:
        logger.exception(
            "Could not create notification for product %s", product.pk
        )

    # Email the vendor when their listing is approved or rejected.
    try:
        send_mail(
            email_subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [vendor.email],
        )
    except Exception:
        logger.exception("Could not email vendor about product %s", product.pk)


def notify_listing_approved(product):
    _notify(
        product,
        Notification.Type.LISTING_APPROVED,
        f"Your product '{product.name}' was approved and is now live on Pawdigree.",
        f"Your product '{product.name}' was approved",
    )


def notify_listing_rejected(product):
    _notify(
        product,
        Notification.Type.LISTING_REJECTED,
        (
            f"Your product '{product.name}' was not approved. "
            f"Reason: {product.rejection_reason} "
            "Edit the product to fix this and it will be reviewed again."
        ),
        f"Your product '{product.name}' needs changes",
    )
