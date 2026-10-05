from django.urls import path

from .views import CustomerRegistrationView


urlpatterns = [
    path(
        'register/customer/',
        CustomerRegistrationView.as_view(),
        name='customer-register',
    ),
]