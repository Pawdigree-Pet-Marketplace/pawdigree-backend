from django.urls import path

from .views import (
    AdminPendingPetListView,
    AdminPetApproveView,
    AdminPetRejectView,
    AdminPetDeactivateView,
    PetDetailView,
    PetListCreateView,
    PublicPetListView,
    PetUpdateView
)

urlpatterns = [
    path("", PetListCreateView.as_view(), name="pet-list"),
    path("public/", PublicPetListView.as_view(), name="pet-public-list"),
    path("admin/<int:pk>/", AdminPetDeactivateView.as_view(), name="pet-admin-detail"),
    path("admin/pending/", AdminPendingPetListView.as_view(), name="pet-admin-pending"),
    path("admin/<int:pk>/approve/", AdminPetApproveView.as_view(), name="pet-admin-approve"),
    path("admin/<int:pk>/reject/", AdminPetRejectView.as_view(), name="pet-admin-reject"),
        path("<int:pk>/", PetDetailView.as_view(), name="pet-detail"),
    path("<int:pk>/edit/", PetUpdateView.as_view(), name="pet-update"),
]
