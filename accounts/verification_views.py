from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    ResendVerificationSerializer,
    VerifyEmailSerializer,
)
from .verification import (
    CODE_TTL,
    RESEND_COOLDOWN,
    check_code,
    read_verification_token,
    seconds_until_resend,
    send_new_code,
)

SESSION_EXPIRED = 'Your session has expired. Please log in again.'
INVALID_CODE = 'Invalid or expired verification code.'


@extend_schema(
    summary='Verify an email address with a one-time code',
    description=(
        'Checks the code emailed at first login. On success the email is '
        'marked verified and login tokens are returned.'
    ),
)
class VerifyEmailView(generics.GenericAPIView):
    serializer_class = VerifyEmailSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'verification'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = read_verification_token(
            serializer.validated_data['verification_token']
        )
        if user is None:
            raise serializers.ValidationError(
                {'verification_token': SESSION_EXPIRED}
            )

        if not check_code(user, serializer.validated_data['code']):
            raise serializers.ValidationError({'code': INVALID_CODE})

        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })


@extend_schema(
    summary='Send a new verification code',
    description=(
        'Replaces the current code with a new one and emails it. '
        'A new code can be requested once every 60 seconds.'
    ),
)
class ResendVerificationView(generics.GenericAPIView):
    serializer_class = ResendVerificationSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'verification_resend'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = read_verification_token(
            serializer.validated_data['verification_token']
        )
        if user is None:
            raise serializers.ValidationError(
                {'verification_token': SESSION_EXPIRED}
            )

        if user.is_email_verified:
            return Response({'detail': 'Email is already verified.'})

        wait = seconds_until_resend(user)
        if wait > 0:
            return Response(
                {
                    'detail': 'Please wait before requesting another code.',
                    'retry_after': wait,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={'Retry-After': str(wait)},
            )

        if not send_new_code(user):
            return Response(
                {'detail': "We couldn't send the email. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            'detail': 'A new verification code has been sent.',
            'expires_in': int(CODE_TTL.total_seconds()),
            'resend_available_in': int(RESEND_COOLDOWN.total_seconds()),
        })