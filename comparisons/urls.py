from django.urls import path

from .views import ListingComparisonView

urlpatterns = [
    path("", ListingComparisonView.as_view(), name="listing-comparison"),
]
