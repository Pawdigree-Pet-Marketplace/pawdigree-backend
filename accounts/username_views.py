from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import User


@extend_schema(
    summary="Check whether a username is free",
    description=(
        "Public check used by the registration forms. Returns only "
        "whether the username is free, nothing else about the account."
    ),
    parameters=[OpenApiParameter("username", str, required=True)],
    responses={
        200: inline_serializer(
            name="UsernameAvailability",
            fields={"available": serializers.BooleanField()},
        )
    },
)
class UsernameAvailableView(APIView):
    permission_classes = (AllowAny,)
    # Ignore any token, so an expired one can't turn a public check into a 401.
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "username_check"

    def get(self, request):
        username = request.query_params.get("username", "").strip()
        if not username:
            raise serializers.ValidationError(
                {"username": "This field is required."}
            )

        max_length = User._meta.get_field("username").max_length
        available = (
            len(username) <= max_length
            and not User.objects.filter(username=username).exists()
        )
        return Response({"available": available})
