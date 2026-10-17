from pathlib import Path

from rest_framework import serializers

from .models import BusinessDocument


MAX_DOCUMENT_SIZE = 10 * 1024 * 1024

ALLOWED_DOCUMENT_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


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
