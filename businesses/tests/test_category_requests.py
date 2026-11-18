
import pytest
from django.urls import reverse
from rest_framework import status

from businesses.models import Business, BusinessCategory
from categories.models import Category


@pytest.mark.django_db
class TestBusinessCategoryRequests:
    """Tests for vendors requesting categories for their businesses."""

    @staticmethod
    def mark_as_pet_business(business):
        business.business_type = Business.BusinessType.PET_SALE_ADOPTION
        business.save(update_fields=["business_type"])

    def test_vendor_can_request_active_categories(
        self, api_client, vendor, business
    ):
        self.mark_as_pet_business(business)
        api_client.force_authenticate(user=vendor)
        category = Category.objects.create(
            name="Pet Food", kind=Category.Kind.PETS, is_active=True
        )

        response = api_client.post(
            reverse(
                "business-category-requests",
                kwargs={"business_id": business.pk},
            ),
            {"category_ids": [category.pk]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert BusinessCategory.objects.filter(
            business=business,
            category=category,
            approval_status=BusinessCategory.ApprovalStatus.PENDING,
        ).exists()

        assert response.data["categories"][0]["category_id"] == category.pk

    def test_vendor_cannot_request_inactive_categories(
        self, api_client, vendor, business
    ):
        self.mark_as_pet_business(business)
        api_client.force_authenticate(user=vendor)
        category = Category.objects.create(
            name="Inactive Category",
            kind=Category.Kind.PETS,
            is_active=False,
        )

        response = api_client.post(
            reverse(
                "business-category-requests",
                kwargs={"business_id": business.pk},
            ),
            {"category_ids": [category.pk]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).exists()

    def test_vendor_cannot_request_categories_for_another_vendors_business(
        self, api_client, vendor, another_vendor, business
    ):
        self.mark_as_pet_business(business)
        api_client.force_authenticate(user=another_vendor)
        category = Category.objects.create(
            name="Pet Toys", kind=Category.Kind.PETS, is_active=True
        )

        response = api_client.post(
            reverse(
                "business-category-requests",
                kwargs={"business_id": business.pk},
            ),
            {"category_ids": [category.pk]},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).exists()

    def test_duplicate_category_ids_do_not_create_duplicate_records(
        self, api_client, vendor, business
    ):
        self.mark_as_pet_business(business)
        api_client.force_authenticate(user=vendor)
        category = Category.objects.create(
            name="Pet Accessories", kind=Category.Kind.PETS, is_active=True
        )

        response = api_client.post(
            reverse(
                "business-category-requests",
                kwargs={"business_id": business.pk},
            ),
            {"category_ids": [category.pk, category.pk]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["categories"]) == 1
        assert BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).count() == 1

    def test_repeating_a_category_request_does_not_create_duplicates(
        self, api_client, vendor, business
    ):
        self.mark_as_pet_business(business)
        api_client.force_authenticate(user=vendor)
        category = Category.objects.create(
            name="Pet Grooming", kind=Category.Kind.PETS, is_active=True
        )
        url = reverse(
            "business-category-requests",
            kwargs={"business_id": business.pk},
        )
        payload = {"category_ids": [category.pk]}

        first_response = api_client.post(url, payload, format="json")
        second_response = api_client.post(url, payload, format="json")

        assert first_response.status_code == status.HTTP_201_CREATED
        assert second_response.status_code == status.HTTP_200_OK
        assert BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).count() == 1

    def test_vendor_cannot_request_category_from_another_business_type(
        self, api_client, vendor, business
    ):
        self.mark_as_pet_business(business)
        api_client.force_authenticate(user=vendor)
        category = Category.objects.create(
            name="Grooming Services", kind=Category.Kind.SERVICES
        )

        response = api_client.post(
            reverse(
                "business-category-requests",
                kwargs={"business_id": business.pk},
            ),
            {"category_ids": [category.pk]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).exists()

    def test_vendor_cannot_request_category_of_wrong_kind(
        self, api_client, vendor, business
    ):
        business.business_type = Business.BusinessType.PRODUCT_SELLER
        business.save(update_fields=["business_type"])
        api_client.force_authenticate(user=vendor)
        category = Category.objects.create(
            name="Dog Walking",
            kind=Category.Kind.SERVICES,
            is_active=True,
        )

        response = api_client.post(
            reverse(
                "business-category-requests",
                kwargs={"business_id": business.pk},
            ),
            {"category_ids": [category.pk]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not BusinessCategory.objects.filter(
            business=business,
            category=category,
        ).exists()
