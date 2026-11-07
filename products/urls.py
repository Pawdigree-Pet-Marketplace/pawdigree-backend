from django.urls import path

from .public import PublicProductDetailView, PublicProductListView
from .views import ProductDetailView, ProductListCreateView

urlpatterns = [
    path("", ProductListCreateView.as_view(), name="product-list"),
    path("public/",PublicProductListView.as_view(),name="product-public-list",),
    path("<int:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path("public/<int:pk>/",PublicProductDetailView.as_view(),name="product-public-detail",),
]
