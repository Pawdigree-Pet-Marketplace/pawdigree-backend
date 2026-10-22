from django.urls import path

from .views import CountryCodeListView

urlpatterns = [
    path("", CountryCodeListView.as_view(), name="country-codes"),
]