from django.urls import path

from . import views

urlpatterns = [
    path("overview/", views.OverviewReportView.as_view(), name="admin-report-overview"),
    path("users/", views.UsersReportView.as_view(), name="admin-report-users"),
    path("pets/", views.PetsReportView.as_view(), name="admin-report-pets"),
    path("product-sales/", views.ProductSalesReportView.as_view(), name="admin-report-product-sales"),
    path("pet-sales/", views.PetSalesReportView.as_view(), name="admin-report-pet-sales"),
    path("saved/", views.SavedReportListCreateView.as_view(), name="admin-report-saved-list"),
    path("saved/<int:pk>/", views.SavedReportDetailView.as_view(), name="admin-report-saved-detail"),
    path("saved/trash/", views.SavedReportTrashListView.as_view(), name="admin-report-saved-trash"),
    path("saved/<int:pk>/restore/", views.SavedReportRestoreView.as_view(), name="admin-report-saved-restore"),
]