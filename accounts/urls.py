from django.urls import path

from .views import CustomerRegistrationView, VendorRegistrationView


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
]