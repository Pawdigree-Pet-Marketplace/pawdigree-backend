from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if user.has_usable_password():
            raise serializers.ValidationError(
                'This account already has a password. Use change-password instead.'
            )
        validate_password(attrs['new_password'], user=user)
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class SetPasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SetPasswordSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'change_password'

    @extend_schema(
        summary='Set a first password',
        description=(
            'For logged-in users whose account has no password yet, such as '
            'accounts created with Google. Accounts that already have a '
            'password must use change-password.'
        ),
        responses={200: OpenApiResponse(description='Password set.')},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])

        return Response({'detail': 'Password set.'})