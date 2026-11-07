from django.urls import path

from .views import (
    CategoryDetailView,
    CategoryListCreateView,
    PublicCategoryListView,
)

urlpatterns = [
    path("", CategoryListCreateView.as_view(), name="category-list"),
    path("public/",PublicCategoryListView.as_view(),name="category-public-list",),
    path("<int:pk>/", CategoryDetailView.as_view(), name="category-detail"),
]