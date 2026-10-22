from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        LISTING_APPROVED = "LISTING_APPROVED", "Listing approved"
        LISTING_REJECTED = "LISTING_REJECTED", "Listing rejected"
        LISTING_PENDING = "LISTING_PENDING", "Listing pending"

    notification_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    user_role = models.CharField(max_length=20, editable=False)
    type = models.CharField(max_length=30, choices=Type.choices)
    message = models.TextField()
    reference_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Id of the object this notification is about, e.g. a pet.",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def save(self, *args, **kwargs):
        # Snapshot the role when the notification is created.
        if not self.user_role:
            self.user_role = self.user.role
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.type} -> {self.user}"
