from django.urls import path

from .views import (
    ProductDetailView,
    ProductImageCreateView,
    ProductImageDeleteView,
    ProductListCreateView,
    PublicProductDetailView,
    PublicProductListView,
)

urlpatterns = [
    path("", ProductListCreateView.as_view(), name="product-list"),
    path("public/",PublicProductListView.as_view(),name="product-public-list",),
    path("public/<int:pk>/",PublicProductDetailView.as_view(),name="product-public-detail",),
    path("<int:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path("<int:product_pk>/images/",ProductImageCreateView.as_view(),name="product-image-create",),
    path("<int:product_pk>/images/<int:pk>/",ProductImageDeleteView.as_view(),name="product-image-delete",),
]