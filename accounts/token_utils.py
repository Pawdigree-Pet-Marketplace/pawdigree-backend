from django.conf import settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

SESSION_CLAIM = 'session_started'


def revoke_user_tokens(user):
    """Blacklist every refresh token issued so far to this user."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class SessionRefreshToken(RefreshToken):
    """A refresh token whose session ends SESSION_MAX_LIFETIME after login.

    Rotation keeps every claim except jti, exp and iat, so the login time
    stored in SESSION_CLAIM carries over to each new token.
    """

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token[SESSION_CLAIM] = int(token.current_time.timestamp())
        return token

    def verify(self):
        super().verify()
        now = int(self.current_time.timestamp())
        started = self.payload.get(SESSION_CLAIM)
        if started is None:
            # Issued before the cap existed: its clock starts now, so
            # nobody is logged out the moment this deploys.
            self.payload[SESSION_CLAIM] = now
            return
        limit = int(settings.SESSION_MAX_LIFETIME.total_seconds())
        if now - int(started) > limit:
            raise TokenError('Your session has ended. Please log in again.')