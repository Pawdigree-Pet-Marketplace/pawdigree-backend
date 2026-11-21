from django.utils.text import slugify  # noqa: F401  (used in views)
from rest_framework import serializers

from .filters import parse_filters
from .models import SavedReport


class SavedReportCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    report_type = serializers.ChoiceField(choices=SavedReport.ReportType.choices)
    filters = serializers.DictField(required=False)

    def validate(self, attrs):
        # Fail early with field-level errors, before any heavy queries.
        try:
            parse_filters(attrs["report_type"], attrs.get("filters", {}))
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"filters": exc.detail})
        return attrs


class SavedReportListSerializer(serializers.ModelSerializer):
    generated_by_email = serializers.EmailField(
        source="generated_by.email", read_only=True, default=None
    )

    class Meta:
        model = SavedReport
        fields = (
            "id", "name", "report_type", "filters",
            "generated_by_email", "created_at",
        )
        read_only_fields = fields


class SavedReportDetailSerializer(SavedReportListSerializer):
    class Meta(SavedReportListSerializer.Meta):
        fields = SavedReportListSerializer.Meta.fields + ("data",)
        read_only_fields = fields
        
class SavedReportTrashSerializer(SavedReportListSerializer):
    deleted_by_email = serializers.EmailField(
        source="deleted_by.email", read_only=True, default=None
    )
    restorable_until = serializers.DateTimeField(read_only=True)

    class Meta(SavedReportListSerializer.Meta):
        fields = SavedReportListSerializer.Meta.fields + (
            "deleted_at", "deleted_by_email", "restorable_until",
        )
        read_only_fields = fields