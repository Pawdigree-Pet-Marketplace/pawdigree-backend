from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """A permanent record of one important system or administrative action.

    `action` is a plain string such as 'pet.updated', so any app can add its
    own actions without a migration. `details` must never hold passwords or
    tokens. The email and label snapshots keep the record readable if the
    account or the target is later deleted.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_entries_performed',
    )
    actor_email = models.EmailField(blank=True)
    actor_role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_label = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-created_at', '-id')

    def __str__(self):
        return f'{self.action} by {self.actor_email or "system"}'
