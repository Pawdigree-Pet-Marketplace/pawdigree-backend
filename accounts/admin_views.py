from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsSystemAdminRoleOnly

from .serializers import AdministratorSerializer, AdminRegistrationSerializer
from .services import set_administrator_active

User = get_user_model()


class AdministratorPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


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
