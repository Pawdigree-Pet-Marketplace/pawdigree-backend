from rest_framework import serializers
from .services import rating_summary

from .models import Review, ReviewReply



def short_name(user) -> str:
    """First name and last initial, so we don't expose full names."""
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if not first:
        return "Customer"
    return f"{first} {last[0]}." if last else first

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
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id", "kind", "target_id", "rating", "comment",
            "reviewer", "created_at", "updated_at", "replies",
        )
        read_only_fields = fields

    def get_reviewer(self, obj) -> str:
        return short_name(obj.customer)

    def get_replies(self, obj) -> list:
        return ReviewReplySerializer(obj.replies.select_related("author"), many=True).data


class ReviewVisibilitySerializer(serializers.Serializer):
    is_visible = serializers.BooleanField()
    
    
class RatingSummaryMixin(serializers.Serializer):
    """Adds average_rating and review_count to a public serializer.
    Set rating_field to "product", "service" or "pet". If the queryset was
    built with with_ratings(), the numbers are already on the object;
    otherwise (a detail page) it asks the database once."""

    rating_field = None
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    def _summary(self, obj):
        if hasattr(obj, "review_count"):
            average = obj.average_rating
            return {
                "average_rating": round(average, 1) if average is not None else None,
                "review_count": obj.review_count,
            }
        return rating_summary(self.rating_field, obj)

    def get_average_rating(self, obj) -> float | None:
        return self._summary(obj)["average_rating"]

    def get_review_count(self, obj) -> int:
        return self._summary(obj)["review_count"]
    
    
class ReviewReplyCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=1000, trim_whitespace=True)


class ReviewReplySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source="author.role", read_only=True)

    class Meta:
        model = ReviewReply
        fields = ("id", "review_id", "author_name", "author_role", "body", "created_at")
        read_only_fields = fields

    def get_author_name(self, obj) -> str:
        return short_name(obj.author)