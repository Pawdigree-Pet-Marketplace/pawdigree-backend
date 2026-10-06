from django.urls import path

from .views import (
    CustomerLoginView,
    CustomerRegistrationView,
    VendorRegistrationView,
)

urlpatterns = [
    ...
]

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
    'login/customer/',
    CustomerLoginView.as_view(),
    name='customer-login',
),
]