import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

User = get_user_model()

INVITE_SALT = 'accounts.admin-invite'
INVITE_MAX_AGE = int(timedelta(days=3).total_seconds())
INVALID_LINK = 'Invalid or expired invitation link.'


def make_invite_token(user):
    return signing.dumps(user.pk, salt=INVITE_SALT)


def read_invite_token(token):
    """Return the invited admin, or None if the link can't be used.

    A link works only while the account has no usable password, so it
    stops working as soon as the admin has set one.
    """
    try:
        user_id = signing.loads(token, salt=INVITE_SALT, max_age=INVITE_MAX_AGE)
    except signing.BadSignature:
        return None
    user = User.objects.filter(
        pk=user_id, role=User.Role.ADMIN, is_active=True
    ).first()
    if user is None or user.has_usable_password():
        return None
    return user


def send_admin_invite(user):
    """Email the admin a one-time link to set their password."""
    portal_url = settings.ADMIN_PORTAL_URL
    context = {
        'user': user,
        'portal_url': portal_url,
        'invite_url': f'{portal_url}/set-password/?token={make_invite_token(user)}',
        'logo_url': settings.EMAIL_LOGO_URL,
    }
    message = EmailMultiAlternatives(
        subject='Your Pawdigree admin account',
        body=render_to_string('accounts/emails/admin_invite.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string('accounts/emails/admin_invite.html', context),
        'text/html',
    )
    try:
        message.send(fail_silently=False)
    except Exception:
        logging.getLogger(__name__).exception(
            'Admin invite email could not be sent for user %s', user.pk
        )


class AdminSetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class AdminSetPasswordView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = AdminSetPasswordSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'admin_set_password'

    @extend_schema(
        summary='Set the password for a new administrator',
        description=(
            'Uses the one-time link emailed when a SYSTEM_ADMIN creates an '
            'administrator. The link expires after 3 days and works once.'
        ),
        responses={200: OpenApiResponse(description='Password set.')},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = read_invite_token(serializer.validated_data['token'])
        if user is None:
            raise serializers.ValidationError({'token': INVALID_LINK})

        new_password = serializer.validated_data['new_password']
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({'new_password': list(error.messages)})

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'detail': 'Password set. You can now log in.'})
