from django.urls import path

from .views import (
    BusinessDocumentDownloadView,
    BusinessDocumentUploadView,
)

urlpatterns = [
    path(
        "",
        BusinessDocumentUploadView.as_view(),
        name="business-document-upload",
    ),
    path(
        "<uuid:document_id>/download/",
        BusinessDocumentDownloadView.as_view(),
        name="business-document-download",
    ),
]
