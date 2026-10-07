from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from rest_framework import serializers


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
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'password',
        ]

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
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'password',
        ]

    def create(self, validated_data):
        return User.objects.create_user(
            role=User.Role.VENDOR,
            **validated_data,
        )

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            self.user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                'No account exists with this email address.'
            )

        return value

    def save(self):
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(self.user)

        return {
            'uid': self.user.pk,
            'token': token,
        }


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.IntegerField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    def validate(self, attrs):
        try:
            user = User.objects.get(pk=attrs['uid'])
        except User.DoesNotExist:
            raise serializers.ValidationError(
                'Invalid password reset request.'
            )

        token_generator = PasswordResetTokenGenerator()

        if not token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError(
                'Invalid or expired password reset token.'
            )

        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()

        return user
