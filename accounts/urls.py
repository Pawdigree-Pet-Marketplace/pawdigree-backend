from django.urls import path

from .views import (
    CustomerLoginView,
    CustomerRegistrationView,
    LogoutView,
    VendorLoginView,
    VendorRegistrationView,
    CustomerProfileView,
    CurrentUserView,
)

urlpatterns = [
    path('register/customer/',CustomerRegistrationView.as_view(),name='customer-register',),
    path('register/vendor/',VendorRegistrationView.as_view(),name='vendor-register',),
    path('login/customer/',CustomerLoginView.as_view(),name='customer-login',),
    path('login/vendor/',VendorLoginView.as_view(),name='vendor-login',),
    path('logout/',LogoutView.as_view(),name='logout', ),
    path('profile/',CustomerProfileView.as_view(), name='customer-profile',),
    path('me/', CurrentUserView.as_view(), name='current-user'),
]
