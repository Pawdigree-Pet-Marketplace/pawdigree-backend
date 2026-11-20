from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(
        source="business.name", read_only=True, default=None
    )

    class Meta:
        model = Notification
        fields = (
            "notification_id",
            "type",
            "message",
            "business_id",
            "business_name",
            "reference_type",
            "reference_id",
            "is_read",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()
    by_business = serializers.DictField(
        child=serializers.IntegerField(), required=False
    )