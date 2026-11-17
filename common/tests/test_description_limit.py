import pytest
from django.core.exceptions import ValidationError

from common.validators import validate_description_length
from pets.serializers import PetSerializer
from products.serializers import ProductSerializer, VendorProductSerializer
from services.serializers import ServiceSerializer, ServiceUpdateSerializer


def words(count):
    return " ".join(["word"] * count)


def test_exactly_300_words_is_allowed():
    validate_description_length(words(300))


def test_empty_description_is_left_to_the_field():
    validate_description_length("")


def test_301_words_is_rejected_with_the_count():
    with pytest.raises(ValidationError) as error:
        validate_description_length(words(301))

    assert "300 words" in str(error.value)
    assert "301" in str(error.value)


def test_one_enormous_word_is_rejected():
    with pytest.raises(ValidationError):
        validate_description_length("a" * 3001)


def test_pet_serializer_rejects_a_long_description():
    serializer = PetSerializer(data={"description": words(301)}, partial=True)

    assert not serializer.is_valid()
    assert "description" in serializer.errors


def test_product_serializer_rejects_a_long_description():
    serializer = ProductSerializer(
        data={"description": words(301)}, partial=True
    )

    assert not serializer.is_valid()
    assert "description" in serializer.errors


def test_vendor_product_serializer_inherits_the_rule():
    serializer = VendorProductSerializer(
        data={"description": words(301)}, partial=True
    )

    assert not serializer.is_valid()
    assert "description" in serializer.errors


def test_service_serializer_rejects_a_long_description():
    serializer = ServiceSerializer(
        data={"description": words(301)}, partial=True
    )

    assert not serializer.is_valid()
    assert "description" in serializer.errors


def test_service_update_serializer_inherits_the_rule():
    serializer = ServiceUpdateSerializer(
        data={"description": words(301)}, partial=True
    )

    assert not serializer.is_valid()
    assert "description" in serializer.errors


def test_300_words_passes_on_products_and_services():
    for serializer_class in (ProductSerializer, ServiceSerializer):
        serializer = serializer_class(
            data={"description": words(300)}, partial=True
        )
        serializer.is_valid()

        assert "description" not in serializer.errors
