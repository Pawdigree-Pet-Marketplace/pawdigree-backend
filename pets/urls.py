from django.urls import path

from .views import (
    AdminPetDeactivateView,
    PetDetailView,
    PetListCreateView,
    PublicPetListView,
)

urlpatterns = [
    path("", PetListCreateView.as_view(), name="pet-list"),
    path("public/", PublicPetListView.as_view(), name="pet-public-list"),
    path("admin/<int:pk>/", AdminPetDeactivateView.as_view(), name="pet-admin-detail"),
    path("<int:pk>/", PetDetailView.as_view(), name="pet-detail"),
]
