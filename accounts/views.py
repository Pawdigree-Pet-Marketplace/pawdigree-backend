import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from common.permissions import IsCustomer, IsSystemAdmin

from .emails import send_welcome_email
from .password_reset import PasswordResetTokenGeneratorService
from .serializers import (
    AdminLoginSerializer,
    AdminRegistrationSerializer,
    CurrentUserSerializer,
    CustomerLoginSerializer,
    CustomerProfileSerializer,
    CustomerRegistrationSerializer,
    GoogleLoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    VendorLoginSerializer,
    VendorRegistrationSerializer,
)
from .token_utils import revoke_user_tokens
from .verification import start_verification

User = get_user_model()


class WelcomeEmailMixin:
    """After a successful registration, send the welcome email."""

    def perform_create(self, serializer):
        user = serializer.save()
        # Send only if the account was actually committed to the database.
        transaction.on_commit(lambda: send_welcome_email(user))


@extend_schema(
    summary='Register a customer',
    description=(
        'Creates a new customer account. '
        'No authentication is required.'
    ),
)
class CustomerRegistrationView(WelcomeEmailMixin, generics.CreateAPIView):
    serializer_class = CustomerRegistrationSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    summary='Register a vendor',
    description=(
        'Creates a new vendor account. '
        'No authentication is required.'
    ),
)
class VendorRegistrationView(WelcomeEmailMixin, generics.CreateAPIView):
    serializer_class = VendorRegistrationSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    summary='Create an administrator account',
    description=(
        'Creates a new administrator account. '
        'Only the system admin (superuser) may use this endpoint.'
    ),
)
class AdminRegistrationView(generics.CreateAPIView):
    serializer_class = AdminRegistrationSerializer
    permission_classes = (IsAuthenticated, IsSystemAdmin)


@extend_schema(
    summary='Customer login',
    description=(
        'Authenticates a customer using email and password '
        'and returns an access token and refresh token.'
    ),
)
class CustomerLoginView(generics.GenericAPIView):
    serializer_class = CustomerLoginSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        if data.get('verification_required'):
            return Response(start_verification(data['user']))

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
        })

@extend_schema(
    summary='Customer login with Google',
    description=(
        'Verifies a Google ID token and returns an access token and '
        'refresh token. A customer account is created on first use.'
    ),
)
class GoogleLoginView(generics.GenericAPIView):
    serializer_class = GoogleLoginSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
        })


@extend_schema(
    summary='Administrator login',
    description=(
        'Authenticates an administrator or system administrator '
        'using email and password and returns an access token '
        'and refresh token.'
    ),
)
class AdminLoginView(generics.GenericAPIView):
    serializer_class = AdminLoginSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
        })


@extend_schema(
    summary='Vendor login',
    description=(
        'Authenticates a vendor using email and password '
        'and returns an access token and refresh token.'
    ),
)
class VendorLoginView(generics.GenericAPIView):
    serializer_class = VendorLoginSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        if data.get('verification_required'):
            return Response(start_verification(data['user']))

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
        })


@extend_schema(
    summary='Logout',
    description=(
        'Logs out the authenticated user by blacklisting '
        'the provided refresh token.'
    ),
)
class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(
            {'detail': 'Successfully logged out.'},
        )


class CustomerProfileView(generics.RetrieveUpdateAPIView):
    # Lets customers retrieve and update their profile information.
    serializer_class = CustomerProfileSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def get_object(self):
        return self.request.user

class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetRequestSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'password_reset'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
        ).first()

        if user:
            token_service = PasswordResetTokenGeneratorService()
            token = token_service.generate_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = (
                f"{settings.FRONTEND_URL}/reset-password/"
                f"?uid={uid}&token={token}"
            )

           # Prepare the data for both email templates.
            context = {
                'user': user,
                'reset_url': reset_url,
                'logo_url': settings.EMAIL_LOGO_URL,
            }

            # Load the plain-text email template.
            text_content = render_to_string(
                'accounts/emails/password_reset.txt',
                context,
            )

            # Load your designed HTML email template.
            html_content = render_to_string(
                'accounts/emails/password_reset.html',
                context,
            )

            # Create the email with the plain-text version.
            email_message = EmailMultiAlternatives(
                subject='Reset your Pawdigree password',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )

          
            # Attach your HTML design as an alternative.
            email_message.attach_alternative(
                html_content,
                'text/html',
            )

            # Send the email.
            # A send failure is logged but never shown to the caller, so
            # the response is the same whether or not the account exists.
            try:
                email_message.send(fail_silently=False)
            except Exception:
                logging.getLogger(__name__).exception(
                    'Password reset email could not be sent for user %s',
                    user.pk,
                )

        return Response(
            {
                'detail': (
                    'If an account exists for that email, '
                    'password reset instructions will be sent.'
                )
            },
            status=200,
        )


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetConfirmSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'password_reset_confirm'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uid = serializer.validated_data.get('uid')
        email = serializer.validated_data.get('email')
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        user = None
        if uid:
            try:
                user = User.objects.filter(
                    pk=force_str(urlsafe_base64_decode(uid)),
                    is_active=True,
                ).first()
            except (TypeError, ValueError, OverflowError):
                user = None
        elif email:
            user = User.objects.filter(
                email__iexact=email,
                is_active=True,
            ).first()
        token_service = PasswordResetTokenGeneratorService()

        if not user or not token_service.validate_token(user, token):
            raise serializers.ValidationError({
                'token': 'Invalid or expired password-reset token.'
            })

        user.set_password(new_password)
        user.save(update_fields=['password'])
        revoke_user_tokens(user)

        return Response(
            {'detail': 'Password has been reset successfully.'},
            status=200,
        )
