import pytest

from categories.models import Category


@pytest.mark.django_db
class TestCategoryModel:
    """Tests for the Category model."""

    def test_category_generates_slug_from_name(self):
        category = Category.objects.create(name="Pet Care")

        assert category.slug == "pet-care"

    def test_duplicate_category_slugs_are_made_unique(self):
        first_category = Category.objects.create(name="Pet Care")
        second_category = Category.objects.create(name="Pet-Care")

        assert first_category.slug == "pet-care"
        assert second_category.slug == "pet-care-2"

    def test_category_is_active_by_default(self):
        category = Category.objects.create(name="Veterinary")

        assert category.is_active is True