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
                "kind": Category.Kind.SERVICES,
                "is_active": True,
            }
        )

        assert serializer.is_valid(), serializer.errors

    def test_duplicate_category_slug_is_rejected(self):
        Category.objects.create(
            name="Pet Care", kind=Category.Kind.SERVICES
        )

        serializer = CategorySerializer(
            data={
                "name": "Pet-Care",
                "description": "Pet care services",
                "kind": Category.Kind.SERVICES,
                "is_active": True,
            }
        )

        assert not serializer.is_valid()
        assert "name" in serializer.errors

    def test_general_kind_is_rejected(self):
        serializer = CategorySerializer(data={
            "name": "Other",
            "kind": "general",
        })

        assert not serializer.is_valid()
        assert "kind" in serializer.errors

    def test_kind_is_required(self):
        serializer = CategorySerializer(data={"name": "Other"})

        assert not serializer.is_valid()
        assert "kind" in serializer.errors
