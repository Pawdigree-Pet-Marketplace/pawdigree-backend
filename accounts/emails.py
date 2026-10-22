import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SUBJECT = "Welcome to Pawdigree"

CUSTOMER_INTRO = (
    "Welcome to the Pawdigree pet marketplace. You're ready to browse, "
    "find your new companion, and buy from trusted sellers."
)
VENDOR_INTRO = (
    "Welcome aboard. You're ready to sell on Pawdigree, reach more pet "
    "lovers, and grow your business."
)


def send_welcome_email(user):
    """Send the welcome email after registration.

    Never raises: a mail problem must not break account creation.
    Returns True if the email was handed to the mail backend.
    """
    if user.role == user.Role.CUSTOMER:
        intro = CUSTOMER_INTRO
    elif user.role == user.Role.VENDOR:
        intro = VENDOR_INTRO
    else:
        # Admins are created by the team, so they get no welcome email.
        return False

    context = {
        "user": user,
        "intro": intro,
        "frontend_url": settings.FRONTEND_URL,
    }

    try:
        text_body = render_to_string("accounts/emails/welcome.txt", context)
        html_body = render_to_string("accounts/emails/welcome.html", context)

        message = EmailMultiAlternatives(
            subject=SUBJECT,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
    except Exception:
        logger.exception("Could not send welcome email to user %s", user.pk)
        return False

    return True