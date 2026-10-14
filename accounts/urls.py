from django.urls import path

from businesses.views import BusinessRegistrationView

from .views import (
    AdminRegistrationView,
    CurrentUserView,
    CustomerLoginView,
    CustomerProfileView,
    CustomerRegistrationView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    VendorLoginView,
    VendorRegistrationView,
)

urlpatterns = [
    path(
        'businesses/register/',
        BusinessRegistrationView.as_view(),
        name='business-register',
    ),
    path('register/customer/',CustomerRegistrationView.as_view(),name='customer-register',),
    path('register/vendor/',VendorRegistrationView.as_view(),name='vendor-register',),
    path('login/customer/',CustomerLoginView.as_view(),name='customer-login',),
    path('login/vendor/',VendorLoginView.as_view(),name='vendor-login',),
    path('logout/',LogoutView.as_view(),name='logout', ),
    path('profile/',CustomerProfileView.as_view(), name='customer-profile',),
    path('current-user/', CurrentUserView.as_view(), name='current-user'),
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/<uidb64>/<token>/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('register/admin/', AdminRegistrationView.as_view(),name='admin-register',),
]
