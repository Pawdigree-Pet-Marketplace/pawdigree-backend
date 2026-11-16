from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsSystemAdminRoleOnly

from .serializers import (
    AdminRegistrationSerializer,
    AdminUserListResponseSerializer,
    AdminUserSerializer,
    AdministratorSerializer,
)
from .services import set_administrator_active

User = get_user_model()


class AdministratorPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


LISTABLE_USER_ROLES = (
    User.Role.CUSTOMER,
    User.Role.VENDOR,
    User.Role.ADMIN,
)


class AdminUserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'summary': self.summary,
            'results': data,
        })


@extend_schema(
    summary='List registered users',
    description=(
        'SYSTEM_ADMIN only. Lists CUSTOMER, VENDOR and regular ADMIN accounts. '
        'SYSTEM_ADMIN and superuser accounts are excluded. Summary counts cover '
        'the complete eligible population, independently of filters and page.'
    ),
    parameters=[
        OpenApiParameter('search', str, description='Search username, name or email.'),
        OpenApiParameter('role', str, description='CUSTOMER, VENDOR or ADMIN.'),
        OpenApiParameter('status', str, description='active or deactivated.'),
        OpenApiParameter('page', int, description='Page number.'),
        OpenApiParameter('page_size', int, description='Page size, maximum 50.'),
    ],
    responses={200: AdminUserListResponseSerializer},
)
class AdminUserListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = (IsAuthenticated, IsSystemAdminRoleOnly)
    pagination_class = AdminUserPagination

    def get_queryset(self):
        queryset = User.objects.filter(
            role__in=LISTABLE_USER_ROLES,
            is_superuser=False,
        )
        summary = queryset.aggregate(
            total=Count('pk'),
            active=Count('pk', filter=Q(is_active=True)),
            deactivated=Count('pk', filter=Q(is_active=False)),
        )
        summary['suspended'] = 0
        self.paginator.summary = summary

        params = self.request.query_params
        role = params.get('role', '').strip()
        if role and role not in LISTABLE_USER_ROLES:
            raise ValidationError({'role': 'Not a valid user role.'})
        if role:
            queryset = queryset.filter(role=role)

        account_status = params.get('status', '').strip()
        status_filters = {'active': True, 'deactivated': False}
        if account_status and account_status not in status_filters:
            raise ValidationError({'status': 'Not a valid account status.'})
        if account_status:
            queryset = queryset.filter(is_active=status_filters[account_status])

        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset.order_by('-date_joined', '-id')


class AdministratorQuerysetMixin:
    """Every endpoint here sees ADMIN accounts only.

    Any other id (customer, vendor, SYSTEM_ADMIN) returns 404, so ids of
    other accounts can't be probed or edited through this API.
    """

    permission_classes = (IsAuthenticated, IsSystemAdminRoleOnly)

    def get_queryset(self):
        return User.objects.filter(role=User.Role.ADMIN).order_by('id')


@extend_schema(
    summary='List or create administrators',
    description='SYSTEM_ADMIN only. POST creates an ADMIN account.',
)
class AdministratorListCreateView(
    AdministratorQuerysetMixin, generics.ListCreateAPIView
):
    pagination_class = AdministratorPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminRegistrationSerializer
        return AdministratorSerializer


@extend_schema(
    summary='Retrieve or update an administrator',
    description=(
        'SYSTEM_ADMIN only. PATCH changes first_name, last_name and phone; '
        'all other fields are ignored.'
    ),
)
class AdministratorDetailView(
    AdministratorQuerysetMixin, generics.RetrieveUpdateAPIView
):
    serializer_class = AdministratorSerializer
    http_method_names = ('get', 'patch', 'head', 'options')


class AdministratorStatusView(
    AdministratorQuerysetMixin, generics.GenericAPIView
):
    """Base for activate and deactivate. Subclasses set `active`."""

    serializer_class = AdministratorSerializer
    active = None

    @extend_schema(request=None, responses=AdministratorSerializer)
    def post(self, request, *args, **kwargs):
        administrator = self.get_object()
        set_administrator_active(
            administrator=administrator,
            actor=request.user,
            active=self.active,
        )
        return Response(self.get_serializer(administrator).data)


@extend_schema(summary='Activate an administrator')
class ActivateAdministratorView(AdministratorStatusView):
    active = True


@extend_schema(summary='Deactivate an administrator')
class DeactivateAdministratorView(AdministratorStatusView):
    active = False
