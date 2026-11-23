from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Report
from .moderation import get_reported_item


def _person(user):
    if user is None:
        return None
    return {"id": user.pk, "name": user.get_full_name().strip() or user.username}


class AdminReportSerializer(serializers.ModelSerializer):
    """A report as an administrator reviews it. Reporter email is not shown."""

    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reporter = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()
    item = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            "id",
            "reason",
            "reason_display",
            "description",
            "reported_item_type",
            "reported_item_id",
            "status",
            "status_display",
            "reporter",
            "item",
            "reviewed_by",
            "reviewed_at",
            "resolution_note",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_reporter(self, obj):
        return _person(obj.reporter)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_reviewed_by(self, obj):
        return _person(obj.reviewed_by)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_item(self, obj):
        """What the report is about, or null for a general report. exists is
        false if the item has since been deleted."""
        if obj.reported_item_type == Report.ReportedItemType.GENERAL:
            return None
        item = get_reported_item(obj)
        if item is None:
            return {"exists": False}
        if obj.reported_item_type == Report.ReportedItemType.REVIEW:
            return {
                "exists": True,
                "id": item.pk,
                "rating": item.rating,
                "comment": item.comment,
                "target_kind": item.target_kind,
                "target_id": item.target_pk,
                "removed": not item.is_visible,
            }
        return {
            "exists": True,
            "id": item.pk,
            "name": item.name,
            "business_id": str(item.business_id),
            "business_name": item.business.name,
            "approved": item.approved,
            "is_active": item.is_active,
            "rejection_reason": item.rejection_reason,
            "removed": (not item.approved) and bool(item.rejection_reason),
        }


class ReportStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[Report.Status.DISMISSED.value, Report.Status.RESOLVED.value]
    )
    note = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, default=""
    )


class RemoveItemSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
