import pytest

from categories.models import Category
from categories.serializers import CategorySerializer


@pytest.mark.django_db
class TestCategorySerializer:
    """Tests for category validation."""

    def test_valid_category_data(self):
        serializer = CategorySerializer(
            data={
                "name": "Veterinary",
                "description": "Veterinary services",
                "is_active": True,
            }
        )

        assert serializer.is_valid(), serializer.errors

    def test_duplicate_category_slug_is_rejected(self):
        Category.objects.create(name="Pet Care")

        serializer = CategorySerializer(
            data={
                "name": "Pet-Care",
                "description": "Pet care services",
                "is_active": True,
            }
        )

        assert not serializer.is_valid()
        assert "name" in serializer.errors