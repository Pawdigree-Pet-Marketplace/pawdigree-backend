from rest_framework import serializers

from .models import AdoptionApplication


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


class AdoptionApplicationSerializer(serializers.ModelSerializer):
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
        )
        read_only_fields = fields