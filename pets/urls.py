from django.urls import path

from .views import PetListCreateView

urlpatterns = [
    path("", PetListCreateView.as_view(), name="pet-list"),
]
