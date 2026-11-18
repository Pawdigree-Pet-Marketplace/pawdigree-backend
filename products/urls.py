from django.urls import path

from .views import (
    AdminVendorPerformanceView,
    AdminPendingProductListView,
    AdminProductApproveView,
    AdminProductPerformanceListView,
    AdminProductRejectView,
    ProductBulkTemplateView,
    ProductBulkUploadView,
    ProductDetailView,
    ProductImageCreateView,
    ProductImageDeleteView,
    ProductListCreateView,
    PublicProductDetailView,
    PublicProductListView,
)

urlpatterns = [
    path("", ProductListCreateView.as_view(), name="product-list"),
    path(
        "bulk-upload/",
        ProductBulkUploadView.as_view(),
        name="product-bulk-upload",
    ),
    path(
        "bulk-upload/template/",
        ProductBulkTemplateView.as_view(),
        name="product-bulk-template",
    ),
    path("public/", PublicProductListView.as_view(), name="product-public-list"),
    path(
        "public/<int:pk>/",
        PublicProductDetailView.as_view(),
        name="product-public-detail",
    ),
    path(
        "admin/pending/",
        AdminPendingProductListView.as_view(),
        name="product-admin-pending",
    ),
    path(
        "admin/<int:pk>/approve/",
        AdminProductApproveView.as_view(),
        name="product-admin-approve",
    ),
    path(
        "admin/<int:pk>/reject/",
        AdminProductRejectView.as_view(),
        name="product-admin-reject",
    ),
    path("<int:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path(
        "<int:product_pk>/images/",
        ProductImageCreateView.as_view(),
        name="product-image-create",
    ),
    path(
        "<int:product_pk>/images/<int:pk>/",
        ProductImageDeleteView.as_view(),
        name="product-image-delete",
    ),
    path("admin/vendors/performance/", AdminVendorPerformanceView.as_view(), name="admin-vendor-performance"),
    path("admin/merchandise/products/", AdminProductPerformanceListView.as_view(), name="admin-product-performance"),
]
