from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def email_image(name):
    """Public URL of an email image (Brevo rejects inline attachments)."""
    return f"{settings.EMAIL_ASSETS_URL}/{name}"
