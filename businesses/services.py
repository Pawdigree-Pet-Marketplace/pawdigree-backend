from .models import Business


def sync_vendor_approval(vendor):
    """Set vendor.approved from the vendor's businesses.

    A vendor is approved while at least one of their businesses is
    active and approved.
    """
    approved = vendor.businesses.filter(
        verification_status=Business.VerificationStatus.APPROVED,
        is_active=True,
    ).exists()

    if vendor.approved != approved:
        vendor.approved = approved
        vendor.save(update_fields=["approved"])

    return approved