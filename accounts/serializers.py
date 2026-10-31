from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from common.phone import normalize_phone_number

from .google_auth import GoogleTokenError, verify_google_token
from .token_utils import revoke_user_tokens

User = get_user_model()


class PhoneValidationMixin:
    """Validates and normalizes the phone field to international format."""

    def validate_phone(self, value):
        return normalize_phone_number(value)


class EmailNormalizationMixin:
    """Stores emails lowercased and rejects case-only duplicates."""

    def validate_email(self, value):
        value = value.strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                'user with this email already exists.'
            )

        return value


def resolve_login_email(email):
    """Return the stored spelling of an email, matched ignoring case."""
    user = User.objects.filter(email__iexact=email).order_by('id').first()
    return user.email if user else email

def unique_username(email):
    """Return a free username built from the part of the email before @."""
    base = email.split('@')[0][:140] or 'user'
    username = base
    counter = 2

    while User.objects.filter(username=username).exists():
        username = f'{base}{counter}'
        counter += 1

    return username


class OptionalUsernameMixin:
    """Lets clients leave username out; one is made from the email."""

    def validate(self, attrs):
        if not attrs.get('username'):
            attrs['username'] = unique_username(attrs['email'])

        return super().validate(attrs)


class CustomerRegistrationSerializer(
    PhoneValidationMixin,
    EmailNormalizationMixin,
    OptionalUsernameMixin,
    serializers.ModelSerializer,
):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
    )

    phone = serializers.CharField(
        required=True,
        max_length=20,
    )

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'password',
        )
        extra_kwargs = {'username': {'required': False}}  # noqa: RUF012

    def create(self, validated_data):
        return User.objects.create_user(
            role=User.Role.CUSTOMER,
            **validated_data,
        )


class VendorRegistrationSerializer(
    PhoneValidationMixin,
    EmailNormalizationMixin,
    OptionalUsernameMixin,
    serializers.ModelSerializer,
):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
    )

    phone = serializers.CharField(
        required=True,
        max_length=20,
    )

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'password',
        )
        extra_kwargs = {'username': {'required': False}}  # noqa: RUF012

    def create(self, validated_data):
        return User.objects.create_user(
            role=User.Role.VENDOR,
            **validated_data,
        )


class AdminRegistrationSerializer(
    PhoneValidationMixin,
    EmailNormalizationMixin,
    serializers.ModelSerializer,
):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
    )

    phone = serializers.CharField(
        required=False,
        max_length=20,
    )

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'password',
            'role',
        )
        read_only_fields = ('id', 'role')

    def create(self, validated_data):
        return User.objects.create_user(
            role=User.Role.ADMIN,
            is_staff=True,
            **validated_data,
        )


class CustomerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
    )

    def validate(self, attrs):
        email = attrs['email']
        password = attrs['password']

        user = authenticate(
            email=resolve_login_email(email),
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if user.role != user.Role.CUSTOMER:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if not user.is_active:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if not user.is_email_verified:
            return {
                'user': user,
                'verification_required': True,
            }

        refresh = RefreshToken.for_user(user)

        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField(write_only=True)

    @staticmethod
    def _unique_username(email):
        return unique_username(email)

    def validate(self, attrs):
        try:
            info = verify_google_token(attrs['credential'])
        except GoogleTokenError as exc:
            raise serializers.ValidationError(str(exc))

        email = (info.get('email') or '').lower()
        if not email:
            raise serializers.ValidationError(
                'Google account has no email address.'
            )

        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            try:
                with transaction.atomic():
                    user = User(
                        username=self._unique_username(email),
                        email=email,
                        first_name=info.get('given_name', ''),
                        last_name=info.get('family_name', ''),
                        role=User.Role.CUSTOMER,
                    )
                    user.set_unusable_password()
                    user.save()
            except IntegrityError:
                # A concurrent request created the account first.
                user = User.objects.filter(email__iexact=email).first()
                if user is None:
                    raise serializers.ValidationError(
                        'Could not sign in. Please try again.'
                    )

        if user.role != User.Role.CUSTOMER:
            raise serializers.ValidationError(
                'Could not sign in. Please try again.'
            )

        if not user.is_active:
            raise serializers.ValidationError('Could not sign in. Please try again.')

        if not user.is_email_verified:
            # Google has verified this email address.
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])

            if user.has_usable_password():
                # This account was never verified, so its password may
                # belong to someone who doesn't own this inbox.
                user.set_unusable_password()
                user.save(update_fields=['password'])
                revoke_user_tokens(user)

        refresh = RefreshToken.for_user(user)

        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

class VendorLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
    )

    def validate(self, attrs):
        email = attrs['email']
        password = attrs['password']

        user = authenticate(
            email=resolve_login_email(email),
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if user.role != user.Role.VENDOR:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if not user.is_active:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if not user.is_email_verified:
            return {
                'user': user,
                'verification_required': True,
            }

        refresh = RefreshToken.for_user(user)

        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
    )

    def validate(self, attrs):
        email = attrs['email']
        password = attrs['password']

        user = authenticate(
            email=resolve_login_email(email),
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if user.role not in (user.Role.ADMIN, user.Role.SYSTEM_ADMIN):
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if not user.is_active:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        refresh = RefreshToken.for_user(user)

        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        try:
            self._token = RefreshToken(attrs['refresh'])
        except TokenError as exc:
            raise serializers.ValidationError(
                'Invalid or expired refresh token.'
            ) from exc

        return attrs

    def save(self, **kwargs):
        self._token.blacklist()


class CurrentUserSerializer(serializers.ModelSerializer):
    isActive = serializers.SerializerMethodField()
    accountStatus = serializers.SerializerMethodField()
    businesses = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'role',
            'is_email_verified',
            'isActive',
            'accountStatus',
            'businesses',
        )
        read_only_fields = fields

    def get_isActive(self, obj) -> bool:
        return obj.is_active

    def get_accountStatus(self, obj) -> str:
        return 'active' if obj.is_active else 'inactive'

    def get_businesses(self, obj) -> list:
        if obj.role != User.Role.VENDOR:
            return []

        return [
            {
                'id': str(business.id),
                'name': business.name,
                'verification_status': business.verification_status,
            }
            for business in obj.businesses.filter(is_active=True)
        ]


class CustomerProfileSerializer(
    PhoneValidationMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
        )

    def validate_username(self, value):
        user = self.instance

        if User.objects.filter(username=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This username is not available.")

        return value

    def validate_email(self, value):
        user = self.instance

        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email already has an account")

        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if not attrs.get('uid') and not attrs.get('email'):
            raise serializers.ValidationError({
                'token': 'Invalid or expired password-reset token.'
            })
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    verification_token = serializers.CharField(write_only=True)
    code = serializers.CharField(write_only=True, max_length=10)


class ResendVerificationSerializer(serializers.Serializer):
    verification_token = serializers.CharField(write_only=True)