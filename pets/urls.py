from django.urls import path

from .views import (
    AdminPendingPetListView,
    AdminPetApproveView,
    AdminPetDeactivateView,
    AdminPetRejectView,
    PetBulkTemplateView,
    PetBulkUploadView,
    PetDetailView,
    PetListCreateView,
    PetUpdateView,
    PublicPetDetailView,
    PublicPetListView,
    PublicPetLocationListView,
)

urlpatterns = [
    path("", PetListCreateView.as_view(), name="pet-list"),
    path("bulk-upload/", PetBulkUploadView.as_view(), name="pet-bulk-upload"),
    path("bulk-upload/template/", PetBulkTemplateView.as_view(), name="pet-bulk-template"),
    path("public/", PublicPetListView.as_view(), name="pet-public-list"),
    path("public/locations/", PublicPetLocationListView.as_view(), name="pet-public-locations"),
    path("public/<int:pk>/", PublicPetDetailView.as_view(), name="pet-public-detail"),
    path("admin/<int:pk>/", AdminPetDeactivateView.as_view(), name="pet-admin-detail"),
    path("admin/pending/", AdminPendingPetListView.as_view(), name="pet-admin-pending"),
    path("admin/<int:pk>/approve/", AdminPetApproveView.as_view(), name="pet-admin-approve"),
    path("admin/<int:pk>/reject/", AdminPetRejectView.as_view(), name="pet-admin-reject"),
    path("<int:pk>/", PetDetailView.as_view(), name="pet-detail"),
    path("<int:pk>/edit/", PetUpdateView.as_view(), name="pet-update"),
]