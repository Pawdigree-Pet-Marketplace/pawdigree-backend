from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.permissions import IsAdmin
from common.permissions import IsVendor

from .models import BusinessDocument
from .serializers import BusinessDocumentUploadSerializer


@extend_schema(
    tags=["documents"],
    summary="Upload a business verification document",
    description=(
        "Allows an authenticated vendor to upload a document "
        "for a business they own."
    ),
)
class BusinessDocumentUploadView(generics.CreateAPIView):
    serializer_class = BusinessDocumentUploadSerializer
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser)

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


@extend_schema(
    tags=["documents"],
    summary="Open a business verification document",
    description="Only administrators can open uploaded documents.",
    responses={200: {"type": "string", "format": "binary"}},
)
class BusinessDocumentDownloadView(APIView):
    permission_classes = (IsAuthenticated, IsAdmin)

    def get(self, request, document_id):
        document = get_object_or_404(
            BusinessDocument.objects.select_related("business"),
            document_id=document_id,
        )

        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=f"business-document-{document.document_id}",
        )
