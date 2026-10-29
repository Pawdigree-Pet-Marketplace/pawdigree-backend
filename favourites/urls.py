from django.urls import path

from .views import FavouriteDetailView, FavouriteIdsView, FavouriteListView

urlpatterns = [
    path("", FavouriteListView.as_view(), name="favourite-list"),
    path("ids/", FavouriteIdsView.as_view(), name="favourite-ids"),
    path("<int:pet_id>/", FavouriteDetailView.as_view(), name="favourite-detail"),
]