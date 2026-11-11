from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .token_utils import revoke_user_tokens


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate_new_password(self, value):
        validate_password(value, user=self.context['request'].user)
        return value

    def validate(self, attrs):
        if attrs['current_password'] == attrs['new_password']:
            raise serializers.ValidationError({
                'new_password': 'The new password must be different from the current one.'
            })
        return attrs


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangePasswordSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'change_password'

    @extend_schema(
        summary='Change my password',
        description=(
            'Any logged-in user. All refresh tokens are revoked, so the '
            'user must log in again.'
        ),
        responses={200: OpenApiResponse(description='Password changed.')},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        revoke_user_tokens(user)

        return Response({'detail': 'Password changed. Please log in again.'})
