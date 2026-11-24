from rest_framework import serializers

from pets.serializers import PublicPetSerializer
from products.serializers import PublicProductDetailSerializer
from services.serializers import PublicServiceSerializer


class ComparisonRequestSerializer(serializers.Serializer):
    listing_type = serializers.ChoiceField(choices=("product", "service", "pet"))
    listing_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=2,
        max_length=3,
    )

    def validate_listing_ids(self, listing_ids):
        if len(set(listing_ids)) != len(listing_ids):
            raise serializers.ValidationError("Duplicate listing IDs are not allowed.")
        return listing_ids


class ComparisonPetSerializer(PublicPetSerializer):
    city_district = serializers.CharField(
        source="business.city_district",
        read_only=True,
    )

    class Meta(PublicPetSerializer.Meta):
        fields = PublicPetSerializer.Meta.fields + ("city_district",)


COMPARISON_SERIALIZERS = {
    "product": PublicProductDetailSerializer,
    "service": PublicServiceSerializer,
    "pet": ComparisonPetSerializer,
}
