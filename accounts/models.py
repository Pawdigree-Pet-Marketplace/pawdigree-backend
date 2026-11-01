from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Upper


class User(AbstractUser):

    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        VENDOR = 'VENDOR', 'Vendor'
        ADMIN = 'ADMIN', 'Admin'
        SYSTEM_ADMIN = 'SYSTEM_ADMIN', 'System Admin'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )
    approved = models.BooleanField(default=False)

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        unique=True,
    )

    is_email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ('username',)

    class Meta(AbstractUser.Meta):
        indexes = [
            models.Index(Upper('email'), name='user_email_upper_idx'),
        ]


class EmailVerificationCode(models.Model):
    """The single active email verification code for a user.

    Only a keyed hash of the code is stored, never the code itself.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='email_verification_code',
    )
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField()


class AdminAuditLog(models.Model):
    """A permanent record of one sensitive administrator action.

    There is deliberately no field that could hold a password or token.
    The email snapshots keep the record readable if an account is deleted.
    """

    class Action(models.TextChoices):
        SYSTEM_ADMIN_CREATED = 'SYSTEM_ADMIN_CREATED', 'System admin created'
        ADMIN_CREATED = 'ADMIN_CREATED', 'Admin created'
        ADMIN_ACTIVATED = 'ADMIN_ACTIVATED', 'Admin activated'
        ADMIN_DEACTIVATED = 'ADMIN_DEACTIVATED', 'Admin deactivated'

    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='admin_actions_performed',
    )
    actor_email = models.EmailField(blank=True)
    target = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='admin_audit_entries',
    )
    target_email = models.EmailField()
    action = models.CharField(max_length=30, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-id')
