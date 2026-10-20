from .models import Notification


def create_notification(user, notification_type, message, reference_id=None):
    """The one function every app uses to create a notification."""
    return Notification.objects.create(
        user=user,
        type=notification_type,
        message=message,
        reference_id=reference_id,
    )