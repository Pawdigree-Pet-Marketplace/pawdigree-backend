from django.urls import path

from .views import (
    FavouriteDetailView,
    FavouriteIdsView,
    FavouriteListView,
    FavouriteProductDetailView,
    FavouriteProductIdsView,
    FavouriteProductListView,
)

urlpatterns = [
    path("", FavouriteListView.as_view(), name="favourite-list"),
    path("ids/", FavouriteIdsView.as_view(), name="favourite-ids"),
    path("<int:pet_id>/", FavouriteDetailView.as_view(), name="favourite-detail"),
    path("products/", FavouriteProductListView.as_view(), name="favourite-product-list"),
    path("products/ids/", FavouriteProductIdsView.as_view(), name="favourite-product-ids"),
    path(
        "products/<int:product_id>/",
        FavouriteProductDetailView.as_view(),
        name="favourite-product-detail",
    ),
]