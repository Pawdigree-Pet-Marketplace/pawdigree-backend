from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
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
    SuspendUserSerializer,
)
from .services import (
    set_administrator_active,
    set_managed_user_active,
    set_managed_user_status,
)

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
        'the complete eligible population, independently of filters and page. '
        'Each result contains id, first_name, last_name, email, role, status '
        'and date_joined; sensitive authentication fields are not returned.'
    ),
    parameters=[
        OpenApiParameter('search', str, description='Search username, name or email.'),
        OpenApiParameter(
            'role',
            str,
            enum=('CUSTOMER', 'VENDOR', 'ADMIN'),
            description='Filter by eligible account role.',
        ),
        OpenApiParameter(
            'status',
            str,
            enum=('active', 'deactivated', 'suspended'),
            description='Filter by account status.',
        ),
        OpenApiParameter(
            'page', int, description='Page number, starting at 1.'
        ),
        OpenApiParameter(
            'page_size', int, description='Page size, default 20 and maximum 50.'
        ),
    ],
    responses={
        200: AdminUserListResponseSerializer,
        400: OpenApiResponse(description='Invalid role or status filter.'),
        401: OpenApiResponse(description='Authentication is required.'),
        403: OpenApiResponse(
            description='Only system administrators may use this endpoint.'
        ),
        404: OpenApiResponse(description='The requested page does not exist.'),
    },
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
            active=Count('pk', filter=Q(status=User.AccountStatus.ACTIVE)),
            deactivated=Count(
                'pk', filter=Q(status=User.AccountStatus.DEACTIVATED)
            ),
            suspended=Count(
                'pk', filter=Q(status=User.AccountStatus.SUSPENDED)
            ),
        )
        self.paginator.summary = summary

        params = self.request.query_params
        role = params.get('role', '').strip()
        if role and role not in LISTABLE_USER_ROLES:
            raise ValidationError({'role': 'Not a valid user role.'})
        if role:
            queryset = queryset.filter(role=role)

        account_status = params.get('status', '').strip()
        status_filters = {value for value, _label in User.AccountStatus.choices}
        if account_status and account_status not in status_filters:
            raise ValidationError({'status': 'Not a valid account status.'})
        if account_status:
            queryset = queryset.filter(status=account_status)

        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset.order_by('-date_joined', '-id')


class ManagedUserStatusView(generics.GenericAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = (IsAuthenticated, IsSystemAdminRoleOnly)
    active = None

    @extend_schema(
        request=None,
        responses={
            200: AdminUserSerializer,
            400: OpenApiResponse(
                description='The requested status change is invalid.'
            ),
            401: OpenApiResponse(description='Authentication is required.'),
            403: OpenApiResponse(
                description='Only system administrators may use this endpoint.'
            ),
            404: OpenApiResponse(
                description='The user was not found or cannot be managed here.'
            ),
        },
    )
    def post(self, request, user_id):
        user = set_managed_user_active(
            user_id=user_id,
            actor=request.user,
            active=self.active,
        )
        return Response(self.get_serializer(user).data)


@extend_schema(
    summary='Activate a customer or vendor account',
    description=(
        'SYSTEM_ADMIN only. Changes an eligible CUSTOMER or VENDOR account to '
        'active. Repeating activation on an already active account is a no-op.'
    ),
)
class ActivateUserView(ManagedUserStatusView):
    active = True


@extend_schema(
    summary='Deactivate a customer or vendor account',
    description=(
        'SYSTEM_ADMIN only. Changes an eligible CUSTOMER or VENDOR account to '
        'deactivated and revokes its outstanding refresh tokens. Repeating '
        'deactivation is a no-op.'
    ),
)
class DeactivateUserView(ManagedUserStatusView):
    active = False


@extend_schema(
    summary='Suspend a customer or vendor account',
    description=(
        'SYSTEM_ADMIN only. Changes an eligible CUSTOMER or VENDOR account to '
        'suspended, revokes outstanding refresh tokens and records the trimmed '
        'reason in the audit log. A repeated suspension is a no-op.'
    ),
    request=SuspendUserSerializer,
    responses={
        200: AdminUserSerializer,
        400: OpenApiResponse(description='A non-empty reason is required.'),
        401: OpenApiResponse(description='Authentication is required.'),
        403: OpenApiResponse(
            description='Only system administrators may use this endpoint.'
        ),
        404: OpenApiResponse(
            description='The user was not found or cannot be managed here.'
        ),
    },
)
class SuspendUserView(generics.GenericAPIView):
    serializer_class = SuspendUserSerializer
    permission_classes = (IsAuthenticated, IsSystemAdminRoleOnly)

    def post(self, request, user_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = set_managed_user_status(
            user_id=user_id,
            actor=request.user,
            status=User.AccountStatus.SUSPENDED,
            reason=serializer.validated_data['reason'],
        )
        return Response(AdminUserSerializer(user).data)


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
