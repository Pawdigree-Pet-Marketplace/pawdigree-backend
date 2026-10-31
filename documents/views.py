from django.http import FileResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin
from common.permissions import IsVendor

from .models import BusinessDocument, BusinessDocumentReview
from .serializers import (
    BusinessDocumentReadSerializer,
    BusinessDocumentResubmissionSerializer,
    BusinessDocumentReviewInputSerializer,
    BusinessDocumentUploadSerializer,
)


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


@extend_schema(
    tags=["documents"],
    summary="Review a business verification document",
    description=(
        "Allows administrators to approve a document or request corrections. "
        "A correction reason is mandatory when requesting changes. "
        "Every review action is recorded in the document review history."
    ),
    request=BusinessDocumentReviewInputSerializer,
    responses={200: BusinessDocumentReadSerializer},
)
class BusinessDocumentReviewView(APIView):
    permission_classes = (IsAuthenticated, IsAdmin)

    @transaction.atomic
    def post(self, request, document_id):
        document = get_object_or_404(
            BusinessDocument.objects.select_for_update(),
            document_id=document_id,
        )

        if document.review_status != BusinessDocument.ReviewStatus.PENDING:
            raise serializers.ValidationError(
                "Only documents pending review can be reviewed."
            )

        serializer = BusinessDocumentReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        correction_reason = serializer.validated_data["correction_reason"]

        if action == BusinessDocumentReview.Action.APPROVE:
            document.review_status = BusinessDocument.ReviewStatus.APPROVED
        else:
            document.review_status = (
                BusinessDocument.ReviewStatus.CHANGES_REQUESTED
            )

        document.correction_reason = correction_reason
        document.reviewed_by = request.user
        document.reviewed_at = timezone.now()
        document.save(update_fields=[
            "review_status",
            "correction_reason",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ])

        BusinessDocumentReview.objects.create(
            document=document,
            reviewed_by=request.user,
            action=action,
            correction_reason=correction_reason,
        )

        return Response(
            BusinessDocumentReadSerializer(document).data,
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["documents"],
    summary="Resubmit a corrected business document",
    description=(
        "Allows a vendor to replace a document after an administrator "
        "has requested corrections. The previous document is retained "
        "as SUPERSEDED, and the replacement is submitted as PENDING."
    ),
    request=BusinessDocumentResubmissionSerializer,
    responses={201: BusinessDocumentReadSerializer},
)
class BusinessDocumentResubmissionView(APIView):
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request, document_id):
        previous_document = get_object_or_404(
            BusinessDocument.objects.select_for_update(),
            document_id=document_id,
            business__vendor=request.user,
        )

        if (
            previous_document.review_status
            != BusinessDocument.ReviewStatus.CHANGES_REQUESTED
        ):
            raise serializers.ValidationError(
                "Only documents with requested corrections "
                "can be resubmitted."
            )

        serializer = BusinessDocumentResubmissionSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        replacement = BusinessDocument.objects.create(
            business=previous_document.business,
            uploaded_by=request.user,
            document_type=previous_document.document_type,
            file=serializer.validated_data["file"],
            version=previous_document.version + 1,
            previous_version=previous_document,
            review_status=BusinessDocument.ReviewStatus.PENDING,
        )

        previous_document.review_status = (
            BusinessDocument.ReviewStatus.SUPERSEDED
        )
        previous_document.save(
            update_fields=["review_status", "updated_at"]
        )

        return Response(
            BusinessDocumentReadSerializer(replacement).data,
            status=status.HTTP_201_CREATED,
        )
