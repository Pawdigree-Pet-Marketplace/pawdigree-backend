from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .google_auth import GoogleTokenError, verify_google_token

User = get_user_model()


class CustomerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
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

    def create(self, validated_data):
        return User.objects.create_user(
            role=User.Role.CUSTOMER,
            **validated_data,
        )


class VendorRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
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

    def create(self, validated_data):
        return User.objects.create_user(
            role=User.Role.VENDOR,
            **validated_data,
        )


class AdminRegistrationSerializer(serializers.ModelSerializer):
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
            email=email,
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if user.role != user.Role.CUSTOMER:
            raise serializers.ValidationError(
                'This login is only available to customers.'
            )

        if not user.is_active:
            raise serializers.ValidationError(
                'This account is inactive.'
            )

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
        base = email.split('@')[0][:140] or 'user'
        username = base
        counter = 2

        while User.objects.filter(username=username).exists():
            username = f'{base}{counter}'
            counter += 1

        return username

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
                'This login is only available to customers.'
            )

        if not user.is_active:
            raise serializers.ValidationError('This account is inactive.')

        if user.has_usable_password():
            # Google has verified the inbox, so any password set earlier
            # may belong to someone else.
            user.set_unusable_password()
            user.save(update_fields=['password'])

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
            email=email,
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if user.role != user.Role.VENDOR:
            raise serializers.ValidationError(
                'This login is only available to vendors.'
            )

        if not user.is_active:
            raise serializers.ValidationError(
                'This account is inactive.'
            )

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
            email=email,
            password=password,
        )

        if user is None:
            raise serializers.ValidationError(
                'Invalid email or password.'
            )

        if user.role not in (user.Role.ADMIN, user.Role.SYSTEM_ADMIN):
            raise serializers.ValidationError(
                'This login is only available to administrators.'
            )

        if not user.is_active:
            raise serializers.ValidationError(
                'This account is inactive.'
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
            refresh_token = RefreshToken(attrs['refresh'])
            refresh_token.blacklist()
        except Exception as exc:
            raise serializers.ValidationError(
                'Invalid or expired refresh token.'
            ) from exc

        return attrs


class CurrentUserSerializer(serializers.ModelSerializer):
    isActive = serializers.SerializerMethodField()
    accountStatus = serializers.SerializerMethodField()

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
            'isActive',
            'accountStatus',
        )
        read_only_fields = fields

    def get_isActive(self, obj) -> bool:
        return obj.is_active

    def get_accountStatus(self, obj) -> str:
        return 'active' if obj.is_active else 'inactive'


class CustomerProfileSerializer(serializers.ModelSerializer):
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

        if User.objects.filter(email=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email already has an account")

        return value

    def validate_phone(self, value):
        # Checks the phone number only contains digits and an optional leading plus sign.
        if not value.lstrip("+").isdigit() or value.count("+") > 1 or ("+" in value and not value.startswith("+")):
            raise serializers.ValidationError("The phone number can only have this format: +########### or ##########")

        if len(value) < 10 or len(value) > 20:
            raise serializers.ValidationError("The phone number must between 10 to 20 digits")

        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    def validate_new_password(self, value):
        validate_password(value)
        return value