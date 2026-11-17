from django.urls import path

from .admin_views import (
    AdminUserListView,
    ActivateUserView,
    ActivateAdministratorView,
    AdministratorDetailView,
    AdministratorListCreateView,
    DeactivateAdministratorView,
    DeactivateUserView,
    SuspendUserView,
)

urlpatterns = [
    path(
        'users/',
        AdminUserListView.as_view(),
        name='admin-user-list',
    ),
    path(
        'users/<int:user_id>/activate/',
        ActivateUserView.as_view(),
        name='admin-user-activate',
    ),
    path(
        'users/<int:user_id>/deactivate/',
        DeactivateUserView.as_view(),
        name='admin-user-deactivate',
    ),
    path(
        'users/<int:user_id>/suspend/',
        SuspendUserView.as_view(),
        name='admin-user-suspend',
    ),
    path(
        'administrators/',
        AdministratorListCreateView.as_view(),
        name='administrator-list',
    ),
    path(
        'administrators/<int:pk>/',
        AdministratorDetailView.as_view(),
        name='administrator-detail',
    ),
    path(
        'administrators/<int:pk>/activate/',
        ActivateAdministratorView.as_view(),
        name='administrator-activate',
    ),
    path(
        'administrators/<int:pk>/deactivate/',
        DeactivateAdministratorView.as_view(),
        name='administrator-deactivate',
    ),
]
