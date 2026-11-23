from rest_framework import serializers

from businesses.models import Business
from common.validators import validate_description_length
from reviews.serializers import RatingSummaryMixin

from .models import Pet, PetImage, PetSearchTerm


class PetImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetImage
        fields = (
            "image_id",
            "image",
            "is_primary",
            "position",
            "created_at",
        )
        read_only_fields = ("image_id", "created_at")


class PetSerializer(serializers.ModelSerializer):
    """Serialize pet listings. Images are saved by the view."""

    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.all(),
    )
    images = PetImageSerializer(many=True, read_only=True)
    review_status = serializers.ReadOnlyField()

    class Meta:
        model = Pet
        fields = (
            "pet_id",
            "vendor",
            "business",
            "listing_type",
            "name",
            "species",
            "breed",
            "age",
            "gender",
            "size",
            "description",
            "approved",
            "review_status",
            "rejection_reason",
            "reviewed_at",
            "is_active",
            "price",
            "adoption_status",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "pet_id",
            "vendor",
            "approved",
            "review_status",
            "rejection_reason",
            "reviewed_at",
            "is_active",
            "created_at",
            "updated_at",            
            "average_rating", 
            "review_count",
        )

    def validate_adoption_status(self, value):
        """RESERVED and SOLD are set by checkout, never by a listing edit."""
        locked = (Pet.AdoptionStatus.RESERVED, Pet.AdoptionStatus.SOLD)
        current = getattr(self.instance, "adoption_status", None)
        if value != current and (value in locked or current in locked):
            raise serializers.ValidationError(
                "This status is set by checkout and cannot be changed here."
            )
        return value

    def validate_description(self, value):
        validate_description_length(value)
        return value

    def validate_business(self, value):
        request = self.context.get("request")

        if request is None or value.vendor_id != request.user.pk:
            raise serializers.ValidationError(
                "You can only list pets under your own business."
            )

        # An existing listing can stay with its business even if that
        # business is later suspended.
        if self.instance is not None and self.instance.business_id == value.pk:
            return value

        if (
            not value.is_active
            or value.verification_status != Business.VerificationStatus.APPROVED
        ):
            raise serializers.ValidationError(
                "Your business must be approved before you can add pet listings."
            )

        if value.business_type != Business.BusinessType.PET_SALE_ADOPTION:
            raise serializers.ValidationError(
                "Only Pet sale and adoption businesses can add pet listings."
            )

        return value

    def validate(self, attrs):
        listing_type = attrs.get(
            "listing_type",
            self.instance.listing_type
            if self.instance
            else Pet.ListingType.ADOPTION,
        )
        price = attrs.get(
            "price",
            self.instance.price if self.instance else None,
        )

        if listing_type == Pet.ListingType.SALE:
            if price is None or price <= 0:
                raise serializers.ValidationError({
                    "price": (
                        "A sale listing must have a price greater than zero."
                    )
                })
        elif listing_type == Pet.ListingType.ADOPTION and price is not None:
            raise serializers.ValidationError({
                "price": "An adoption listing must not have a price."
            })

        return attrs


class AdminPetSerializer(PetSerializer):
    """What administrators see: a listing plus its business's name."""

    business_name = serializers.CharField(source="business.name", read_only=True)

    class Meta(PetSerializer.Meta):
        fields = PetSerializer.Meta.fields + ("business_name",)


class AdminPetUpdateSerializer(AdminPetSerializer):
    """Admin corrections to a listing.

    The business and owner can't be changed, and neither can the review
    or active state; the admin uses the approve, reject and remove
    actions for those.
    """

    business = serializers.PrimaryKeyRelatedField(read_only=True)


class AdminPetCreateSerializer(PetSerializer):
    """Create a listing on behalf of any approved pet sale business."""

    def validate_business(self, value):
        if (
            not value.is_active
            or value.verification_status != Business.VerificationStatus.APPROVED
        ):
            raise serializers.ValidationError(
                "The business must be approved and active."
            )

        if value.business_type != Business.BusinessType.PET_SALE_ADOPTION:
            raise serializers.ValidationError(
                "Only Pet sale and adoption businesses can have pet listings."
            )

        return value


class PublicPetSerializer(RatingSummaryMixin, serializers.ModelSerializer):
    """Customer-facing listing: no vendor id and no internal flags."""
    
    rating_field = "pet"
    images = PetImageSerializer(many=True, read_only=True)
    business_name = serializers.CharField(source="business.name", read_only=True)

    class Meta:
        model = Pet
        fields = (
            "pet_id",
            "business",
            "business_name",
            "listing_type",
            "name",
            "species",
            "breed",
            "age",
            "gender",
            "size",
            "description",
            "price",
            "adoption_status",
            "images",
            "created_at",
        )
        read_only_fields = fields

class PetImageEditSerializer(serializers.Serializer):
    """Image instructions sent along with a listing edit."""

    remove_image_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
    )
    primary_image_id = serializers.IntegerField(required=False)


class PetRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)

class PetBusinessOptionSerializer(serializers.ModelSerializer):
    """Just the id and name, for the admin Create Pet Listing dropdown."""

    class Meta:
        model = Business
        fields = ("id", "name")
        read_only_fields = fields

class TrendingSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetSearchTerm
        fields = ("term", "count")