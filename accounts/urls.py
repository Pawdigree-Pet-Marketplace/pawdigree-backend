from django.urls import path

from businesses.views import BusinessRegistrationView

from .admin_invites import AdminSetPasswordView
from .change_password import ChangePasswordView
from .username_views import UsernameAvailableView
from .verification_views import (
    ResendVerificationView,
    VerifyEmailView,
)
from .views import (
    AdminLoginView,
    CurrentUserView,
    CustomerLoginView,
    CustomerProfileView,
    CustomerRegistrationView,
    GoogleLoginView,
    LogoutView,
    PasswordResetConfirmLinkView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    SessionTokenRefreshView,
    VendorLoginView,
    VendorRegistrationView,
)

urlpatterns = [
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('verify-email/resend/', ResendVerificationView.as_view(), name='verify-email-resend'),
    path('username-available/', UsernameAvailableView.as_view(), name='username-available'),
    path('businesses/register/',BusinessRegistrationView.as_view(),name='business-register',),
    path('register/customer/',CustomerRegistrationView.as_view(),name='customer-register',),
    path('register/vendor/',VendorRegistrationView.as_view(),name='vendor-register',),
    path('login/customer/',CustomerLoginView.as_view(),name='customer-login',),
    path('login/google/', GoogleLoginView.as_view(), name='google-login'),
    path('login/vendor/',VendorLoginView.as_view(),name='vendor-login',),
    path('login/admin/', AdminLoginView.as_view(), name='admin-login',),
    path('logout/',LogoutView.as_view(),name='logout', ),
    path('profile/',CustomerProfileView.as_view(), name='customer-profile',),
    path('current-user/', CurrentUserView.as_view(), name='current-user'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('admin/set-password/', AdminSetPasswordView.as_view(), name='admin-set-password'),
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm-uid'),
    path('password-reset/confirm/<str:uidb64>/<str:token>/', PasswordResetConfirmLinkView.as_view(), name='password-reset-confirm'),
    path('token/refresh/', SessionTokenRefreshView.as_view(), name='token-refresh'),
]