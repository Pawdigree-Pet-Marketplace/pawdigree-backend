from django.urls import path

from .views import BusinessDetailView, BusinessListCreateView

urlpatterns = [
    path("", BusinessListCreateView.as_view(), name="business-list"),
    path("<uuid:pk>/", BusinessDetailView.as_view(), name="business-detail"),
]