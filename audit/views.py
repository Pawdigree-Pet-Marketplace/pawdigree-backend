from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination

from common.permissions import IsAdmin

from .filters import filter_audit_logs
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@extend_schema(
    tags=['audit'],
    summary='List audit log entries (administrators)',
    description='Newest first. Only ADMIN and SYSTEM_ADMIN accounts.',
    parameters=[
        OpenApiParameter(
            'user', str, description='Account id, or part of the actor email.'
        ),
        OpenApiParameter(
            'action',
            str,
            description='One action or a comma-separated list.',
        ),
        OpenApiParameter('date_from', str, description='YYYY-MM-DD, inclusive.'),
        OpenApiParameter('date_to', str, description='YYYY-MM-DD, inclusive.'),
    ],
)
class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = (IsAdmin,)
    pagination_class = AuditLogPagination

    def get_queryset(self):
        return filter_audit_logs(
            AuditLog.objects.all(), self.request.query_params
        )
