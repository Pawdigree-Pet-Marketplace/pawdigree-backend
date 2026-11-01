from django.urls import path

from .admin_views import (
    ActivateAdministratorView,
    AdministratorDetailView,
    AdministratorListCreateView,
    DeactivateAdministratorView,
)

urlpatterns = [
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
