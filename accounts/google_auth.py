from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class GoogleTokenError(Exception):
    """Raised when a Google ID token cannot be accepted."""


def verify_google_token(token):
    """Return the verified Google profile for an ID token."""
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleTokenError('Google sign-in is not configured.')

    try:
        info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except (ValueError, GoogleAuthError) as exc:
        raise GoogleTokenError('Invalid Google token.') from exc

    if not info.get('email_verified'):
        raise GoogleTokenError('Google account email is not verified.')

    return info