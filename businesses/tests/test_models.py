import pytest

from businesses.models import Business


@pytest.mark.django_db
class TestBusinessModel:
    """Tests for the Business model."""

    def test_business_defaults_to_draft_status(self, business):
        assert (
            business.verification_status
            == Business.VerificationStatus.DRAFT
        )

    def test_business_belongs_to_its_vendor(self, vendor, business):
        assert business.vendor == vendor
        assert business in vendor.owned_businesses.all()