from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from accounts.permissions import IsCustomer, IsVendor

from .serializers import (
    CustomerLoginSerializer,
    CustomerRegistrationSerializer,
    LogoutSerializer,
    VendorLoginSerializer,
    VendorRegistrationSerializer,
    CustomerProfileSerializer,

)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from rest_framework import serializers

from .password_reset import PasswordResetTokenGeneratorService
from .serializers import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)

User = get_user_model()


@extend_schema(
    summary='Register a customer',
    description=(
        'Creates a new customer account. '
        'No authentication is required.'
    ),
)
class CustomerRegistrationView(generics.CreateAPIView):
    serializer_class = CustomerRegistrationSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    summary='Register a vendor',
    description=(
        'Creates a new vendor account. '
        'No authentication is required.'
    ),
)
class VendorRegistrationView(generics.CreateAPIView):
    serializer_class = VendorRegistrationSerializer
    permission_classes = (AllowAny,)


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

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response(
            {'detail': 'Successfully logged out.'},
        )

class CustomerProfileView(generics.RetrieveUpdateAPIView): #this view allows customers to retrieve and update their profile information

    serializer_class = CustomerProfileSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def get_object(self):
        return self.request.user


class CurrentUserView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = request.user

        return Response({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
        })


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetRequestSerializer

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
            reset_url = (
                f"{settings.FRONTEND_URL}/reset-password/"
                f"?uid={user.pk}&token={token}"
            )

            send_mail(
                subject='Reset your Pawdigree password',
                message=(
                    'We received a request to reset your password. '
                    f'Use this link to continue: {reset_url}'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
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

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

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

        return Response(
            {'detail': 'Password has been reset successfully.'},
            status=200,
        )


