from django.urls import path

from .views import (
    BusinessDocumentDownloadView,
    BusinessDocumentReviewView,
    BusinessDocumentResubmissionView,
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
    path(
        "<uuid:document_id>/review/",
        BusinessDocumentReviewView.as_view(),
        name="business-document-review",
    ),
    path(
        "<uuid:document_id>/resubmit/",
        BusinessDocumentResubmissionView.as_view(),
        name="business-document-resubmit",
    ),
]
