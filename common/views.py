from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(
    summary='Check that the API is awake',
    description=(
        'Returns immediately without touching the database or checking '
        'login tokens. The frontend can call it first to wake a sleeping '
        'server, and hosting platforms can use it as a health check.'
    ),
    responses=OpenApiTypes.OBJECT,
)
class HealthView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()

    def get(self, request, *args, **kwargs):
        return Response({'status': 'ok'})