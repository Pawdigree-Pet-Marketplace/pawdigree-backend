from django.urls import path

from .views import (
    CustomerRegistrationView,
    VendorRegistrationView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)


urlpatterns = [
    path(
        'register/customer/',
        CustomerRegistrationView.as_view(),
        name='customer-register',
    ),
    
    path(
        'register/vendor/',
        VendorRegistrationView.as_view(),
        name='vendor-register',
    ),

    path(
        'password-reset/',
        PasswordResetRequestView.as_view(),
        name='password-reset-request',
    ),

    path(
        'password-reset/confirm/',
        PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
]