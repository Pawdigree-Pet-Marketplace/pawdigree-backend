import pytest
from django.db import IntegrityError, transaction

from categories.models import Category


@pytest.mark.django_db
class TestCategoryModel:
    """Tests for the Category model."""

    def test_category_generates_slug_from_name(self):
        category = Category.objects.create(
            name="Pet Care", kind=Category.Kind.SERVICES
        )

        assert category.slug == "pet-care"

    def test_duplicate_category_slugs_are_made_unique(self):
        first_category = Category.objects.create(
            name="Pet Care", kind=Category.Kind.SERVICES
        )
        second_category = Category.objects.create(
            name="Pet-Care", kind=Category.Kind.SERVICES
        )

        assert first_category.slug == "pet-care"
        assert second_category.slug == "pet-care-2"

    def test_category_is_active_by_default(self):
        category = Category.objects.create(
            name="Veterinary", kind=Category.Kind.SERVICES
        )

        assert category.is_active is True

    def test_database_rejects_unsupported_kind(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            Category.objects.create(name="Unsupported", kind="general")
