import phonenumbers
from django.conf import settings
from rest_framework import serializers

INVALID_PHONE_MESSAGE = (
    "Enter a valid phone number including the country code, "
    "e.g. +256700123456."
)


def normalize_phone_number(value):
    """Validate a phone number and return it in E.164 format.

    Numbers without a leading + are read as belonging to
    PHONENUMBER_DEFAULT_REGION (Uganda).
    """
    region = getattr(settings, "PHONENUMBER_DEFAULT_REGION", None)

    try:
        number = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise serializers.ValidationError(INVALID_PHONE_MESSAGE) from exc

    if not phonenumbers.is_valid_number(number):
        raise serializers.ValidationError(INVALID_PHONE_MESSAGE)

    return phonenumbers.format_number(
        number,
        phonenumbers.PhoneNumberFormat.E164,
    )