from rest_framework import serializers

from .models import Review


class ReviewCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("product", "service", "pet"))
    target_id = serializers.IntegerField(min_value=1)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, trim_whitespace=True
    )


class ReviewUpdateSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    comment = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, trim_whitespace=True
    )

    class Meta:
        model = Review
        fields = ("rating", "comment")


class ReviewSerializer(serializers.ModelSerializer):
    kind = serializers.CharField(source="target_kind", read_only=True)
    target_id = serializers.IntegerField(source="target_pk", read_only=True)
    reviewer = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id", "kind", "target_id", "rating", "comment",
            "reviewer", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_reviewer(self, obj) -> str:
        """First name and last initial, so we don't expose full names."""
        first = (obj.customer.first_name or "").strip()
        last = (obj.customer.last_name or "").strip()
        if not first:
            return "Customer"
        return f"{first} {last[0]}." if last else first


class ReviewVisibilitySerializer(serializers.Serializer):
    is_visible = serializers.BooleanField()