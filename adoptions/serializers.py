from rest_framework import serializers

from .models import AdoptionApplication, AdoptionInfoMessage


class AdoptionApplicationCreateSerializer(serializers.Serializer):
    pet = serializers.IntegerField()
    home_type = serializers.ChoiceField(
        choices=AdoptionApplication.HomeType.choices
    )
    has_outdoor_space = serializers.BooleanField()
    has_other_pets = serializers.BooleanField()
    other_pets_details = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )
    previous_pet_experience = serializers.ChoiceField(
        choices=AdoptionApplication.Experience.choices
    )
    message = serializers.CharField(max_length=2000)



class InfoMessageSerializer(serializers.ModelSerializer):
    """One request or reply.

    The author is left out on purpose, so no account details leak:
    'kind' already says who wrote it.
    """

    class Meta:
        model = AdoptionInfoMessage
        fields = ('id', 'kind', 'body', 'created_at')
        read_only_fields = fields


class InfoMessageInputSerializer(serializers.Serializer):
    """Validates the text of a request or a reply."""

    # CharField refuses blank text and trims spaces at both ends, so a
    # message made only of spaces is rejected.
    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    
    
    
class AdoptionApplicationSerializer(serializers.ModelSerializer):
    
    # The whole exchange, oldest first.
    info_messages = InfoMessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = AdoptionApplication
        fields = (
            'application_id',
            'pet',
            'status',
            'home_type',
            'has_outdoor_space',
            'has_other_pets',
            'other_pets_details',
            'previous_pet_experience',
            'message',
            'created_at',
            'info_messages',
        )
        read_only_fields = fields

        
class AdoptionDecisionUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            AdoptionApplication.Status.APPROVED,
            AdoptionApplication.Status.REJECTED,
        ]
    )
    decision_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )


class AdoptionDecisionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdoptionApplication
        fields = (
            'application_id',
            'pet',
            'status',
            'decided_by',
            'decided_at',
            'decision_reason',
        )
        read_only_fields = fields

class VendorAdoptionApplicationSerializer(serializers.ModelSerializer):
    customer_id = serializers.ReadOnlyField()
    customer_username = serializers.ReadOnlyField(source="customer.username")
    customer_email = serializers.ReadOnlyField(source="customer.email")
    pet_name = serializers.ReadOnlyField(source="pet.name")
    info_messages = InfoMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AdoptionApplication
        fields = (
            "application_id",
            "pet",
            "pet_name",
            "customer_id",
            "customer_username",
            "customer_email",
            "status",
            "home_type",
            "has_outdoor_space",
            "has_other_pets",
            "other_pets_details",
            "previous_pet_experience",
            "message",
            "created_at",
            "decided_at",
            "decision_reason",
            "info_messages",
        )
        read_only_fields = fields
