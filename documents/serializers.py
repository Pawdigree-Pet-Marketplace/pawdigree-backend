from pathlib import Path

from rest_framework import serializers

from .models import BusinessDocument, BusinessDocumentReview


MAX_DOCUMENT_SIZE = 10 * 1024 * 1024

ALLOWED_DOCUMENT_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


def validate_document_file(uploaded_file):
    if uploaded_file.size > MAX_DOCUMENT_SIZE:
        raise serializers.ValidationError(
            "Documents must not exceed 10 MB."
        )

    extension = Path(uploaded_file.name).suffix.lower()
    signatures = ALLOWED_DOCUMENT_SIGNATURES.get(extension)

    if signatures is None:
        raise serializers.ValidationError(
            "Only PDF, JPEG, and PNG files are allowed."
        )

    header = uploaded_file.read(16)
    uploaded_file.seek(0)

    if not any(header.startswith(signature) for signature in signatures):
        raise serializers.ValidationError(
            "The file contents do not match an allowed file type."
        )

    return uploaded_file


class BusinessDocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessDocument
        fields = (
            "document_id",
            "business",
            "document_type",
            "file",
            "created_at",
        )
        read_only_fields = ("document_id", "created_at")

    def validate_business(self, business):
        request = self.context.get("request")

        if (
            request is None
            or not request.user.is_authenticated
            or business.vendor_id != request.user.pk
        ):
            raise serializers.ValidationError(
                "You can only upload documents for your own business."
            )

        return business

    def validate_file(self, uploaded_file):
        return validate_document_file(uploaded_file)


class BusinessDocumentReadSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessDocument
        fields = (
            "document_id",
            "document_type",
            "review_status",
            "correction_reason",
            "version",
            "reviewed_at",
            "created_at",
            "download_url",
        )
        read_only_fields = fields

    def get_download_url(self, obj) -> str:
        from django.urls import reverse

        return reverse(
            "business-document-download",
            kwargs={"document_id": obj.document_id},
        )


class BusinessDocumentReviewInputSerializer(serializers.Serializer):
    """Validates an administrator's decision on a business document."""

    action = serializers.ChoiceField(
        choices=BusinessDocumentReview.Action.choices,
    )
    correction_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=5000,
    )

    def validate(self, attrs):
        action = attrs["action"]
        reason = attrs.get("correction_reason", "")

        if (
            action == BusinessDocumentReview.Action.REQUEST_CHANGES
            and not reason
        ):
            raise serializers.ValidationError({
                "correction_reason": (
                    "A correction reason is required when requesting changes."
                )
            })

        attrs["correction_reason"] = (
            reason
            if action == BusinessDocumentReview.Action.REQUEST_CHANGES
            else ""
        )

        return attrs


class BusinessDocumentResubmissionSerializer(serializers.Serializer):
    """Validates a vendor's replacement verification document."""

    file = serializers.FileField(required=True)

    def validate_file(self, uploaded_file):
        return validate_document_file(uploaded_file)
