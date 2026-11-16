from .models import AuditLog


def record(*, actor, action, target=None, details=None):
    """Write one audit entry. Call this inside the action's transaction.

    `actor` is None for actions run from the server. `target` is any model
    instance (a pet, a product, a user). Never put passwords or tokens in
    `details`.
    """
    return AuditLog.objects.create(
        actor=actor,
        actor_email=actor.email if actor else '',
        actor_role=getattr(actor, 'role', '') if actor else '',
        action=action,
        target_type=target._meta.label_lower if target is not None else '',
        target_id=str(target.pk) if target is not None else '',
        target_label=str(target)[:255] if target is not None else '',
        details=details or {},
    )
