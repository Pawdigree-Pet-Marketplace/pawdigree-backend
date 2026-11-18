import pytest
from django.urls import reverse
from rest_framework import status

from businesses.models import Business


@pytest.mark.django_db
class TestAdminPetBusinessList:
    """Tests for the admin dropdown of pet sale and adoption businesses."""

    url = "pet-admin-businesses"

    @staticmethod
    def set_business(vendor_business, business_type, status_value, is_active=True):
        vendor_business.business_type = business_type
        vendor_business.verification_status = status_value
        vendor_business.is_active = is_active
        vendor_business.save(
            update_fields=["business_type", "verification_status", "is_active"]
        )

    def test_admin_sees_only_approved_active_pet_businesses(
        self, api_client, admin_user, vendor_business
    ):
        self.set_business(
            vendor_business,
            Business.BusinessType.PET_SALE_ADOPTION,
            Business.VerificationStatus.APPROVED,
        )
        api_client.force_authenticate(user=admin_user)

        response = api_client.get(reverse(self.url))

        assert response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in response.data] == [str(vendor_business.pk)]
        assert set(response.data[0]) == {"id", "name"}

    @pytest.mark.parametrize(
        "business_type, status_value, is_active",
        [
            (
                Business.BusinessType.PET_SALE_ADOPTION,
                Business.VerificationStatus.PENDING,
                True,
            ),
            (
                Business.BusinessType.PET_SALE_ADOPTION,
                Business.VerificationStatus.APPROVED,
                False,
            ),
            (
                Business.BusinessType.PRODUCT_SELLER,
                Business.VerificationStatus.APPROVED,
                True,
            ),
        ],
    )
    def test_other_businesses_are_left_out(
        self, api_client, admin_user, vendor_business,
        business_type, status_value, is_active,
    ):
        self.set_business(vendor_business, business_type, status_value, is_active)
        api_client.force_authenticate(user=admin_user)

        response = api_client.get(reverse(self.url))

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_vendor_is_forbidden(self, api_client, vendor):
        api_client.force_authenticate(user=vendor)

        response = api_client.get(reverse(self.url))

        assert response.status_code == status.HTTP_403_FORBIDDEN