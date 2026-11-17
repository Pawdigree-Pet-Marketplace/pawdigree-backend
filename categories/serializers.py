from django.utils.text import slugify
from rest_framework import serializers

from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    """Validates and serializes marketplace categories."""

    kind = serializers.ChoiceField(choices=Category.Kind.choices, required=True)

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "kind",
            "is_active",
        )
        read_only_fields = ("id", "slug")

    def validate_name(self, value):
        normalized_slug = slugify(value)

        duplicates = Category.objects.filter(slug=normalized_slug)

        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)

        if duplicates.exists():
            raise serializers.ValidationError(
                "A category with a similar name already exists."
            )

        return value
