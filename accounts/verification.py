import hashlib
import hmac
import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from .models import EmailVerificationCode, User
from .emails import send_verification_email

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)

TOKEN_SALT = 'email-verification'
TOKEN_MAX_AGE_SECONDS = 30 * 60


def _hash_code(user, code):
    """Keyed hash, so a leaked database can't be used to recover codes."""
    message = f'{user.pk}:{code}'.encode()
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def issue_code(user):
    """Create a new code for the user, replacing any previous one.

    Returns the plain code so it can be emailed. It is not stored.
    """
    code = f'{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}'
    now = timezone.now()
    EmailVerificationCode.objects.update_or_create(
        user=user,
        defaults={
            'code_hash': _hash_code(user, code),
            'expires_at': now + CODE_TTL,
            'attempts': 0,
            'last_sent_at': now,
        },
    )
    return code


def seconds_until_resend(user):
    """Seconds the user must still wait before a new code can be sent."""
    record = EmailVerificationCode.objects.filter(user=user).first()
    if record is None:
        return 0
    remaining = (
        record.last_sent_at + RESEND_COOLDOWN - timezone.now()
    ).total_seconds()
    return max(0, math.ceil(remaining))


@transaction.atomic
def check_code(user, code):
    """Check a submitted code. Marks the email verified when it is right.

    Every failure looks the same to the caller: wrong code, expired code,
    no code, or too many attempts.
    """
    record = (
        EmailVerificationCode.objects.select_for_update()
        .filter(user=user)
        .first()
    )
    if record is None:
        return False

    if record.expires_at <= timezone.now():
        record.delete()
        return False

    if record.attempts >= MAX_ATTEMPTS:
        return False

    # Count the attempt before comparing, so guesses always use one up.
    record.attempts += 1
    record.save(update_fields=['attempts'])

    submitted = _hash_code(user, (code or '').strip())
    if not hmac.compare_digest(record.code_hash, submitted):
        return False

    record.delete()
    user.is_email_verified = True
    user.save(update_fields=['is_email_verified'])
    return True


def make_verification_token(user):
    """Signed, short-lived value that identifies who is verifying."""
    return signing.dumps({'uid': user.pk}, salt=TOKEN_SALT)


def read_verification_token(token):
    """Return the active user for a valid token, otherwise None."""
    try:
        data = signing.loads(
            token,
            salt=TOKEN_SALT,
            max_age=TOKEN_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        return None

    return User.objects.filter(pk=data.get('uid'), is_active=True).first()


def mask_email(email):
    """v***@example.com, so the screen can say where the code went."""
    name, _, domain = email.partition('@')
    return f'{name[:1]}***@{domain}'


def start_verification(user):
    """Send a code unless one was just sent, and build the login response."""
    if seconds_until_resend(user) == 0:
        code = issue_code(user)
        send_verification_email(
            user,
            code,
            expires_minutes=int(CODE_TTL.total_seconds() // 60),
        )

    return {
        'verification_required': True,
        'verification_token': make_verification_token(user),
        'email': mask_email(user.email),
        'expires_in': int(CODE_TTL.total_seconds()),
        'resend_available_in': seconds_until_resend(user),
    }
