import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from businesses.models import Business, BusinessCategory
from categories.models import Category

URL_NAME = "business-verification-status"


def make_business(vendor, name, **extra):
    return Business.objects.create(
        vendor=vendor,
        name=name,
        description="Pet care services",
        contact="+256700123456",
        email=f"{name.lower().replace(' ', '-')}@example.com",
        address="Kampala Road",
        city_district="Kampala",
        **extra,
    )


def make_category(name):
    return Category.objects.create(name=name, description=f"{name} services")


def get_results(response):
    if isinstance(response.data, dict):
        return response.data["results"]

    return response.data


def find(results, name):
    return next(item for item in results if item["name"] == name)


@pytest.mark.django_db
def test_vendor_sees_status_of_each_own_business(api_client, vendor):
    make_business(vendor, "Draft Shop")
    make_business(
        vendor,
        "Approved Shop",
        verification_status=Business.VerificationStatus.APPROVED,
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))
    results = get_results(response)

    assert response.status_code == status.HTTP_200_OK
    assert len(results) == 2
    assert find(results, "Draft Shop")["verification_status"] == "draft"
    assert find(results, "Approved Shop")["verification_status"] == "approved"


@pytest.mark.django_db
def test_vendor_does_not_see_other_vendors_businesses(
    api_client, vendor, another_vendor
):
    make_business(vendor, "My Shop")
    make_business(another_vendor, "Other Shop")
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))

    assert {item["name"] for item in get_results(response)} == {"My Shop"}


@pytest.mark.django_db
def test_vendor_sees_admin_decision_and_review_time(api_client, vendor):
    make_business(
        vendor,
        "Needs Changes",
        verification_status=Business.VerificationStatus.CHANGES_REQUESTED,
        decision_reason="Upload a clearer registration document.",
        reviewed_at=timezone.now(),
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))
    item = find(get_results(response), "Needs Changes")

    assert item["verification_status"] == "changes_requested"
    assert item["decision_reason"] == "Upload a clearer registration document."
    assert item["reviewed_at"] is not None


@pytest.mark.django_db
def test_can_sell_needs_approved_business_and_approved_category(
    api_client, vendor
):
    business = make_business(
        vendor,
        "Approved Shop",
        verification_status=Business.VerificationStatus.APPROVED,
    )
    BusinessCategory.objects.create(
        business=business,
        category=make_category("Veterinary"),
        approval_status=BusinessCategory.ApprovalStatus.APPROVED,
    )
    BusinessCategory.objects.create(
        business=business,
        category=make_category("Pet Food"),
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))
    item = find(get_results(response), "Approved Shop")
    categories = {entry["name"]: entry for entry in item["categories"]}

    assert categories["Veterinary"]["approval_status"] == "approved"
    assert categories["Veterinary"]["can_sell"] is True
    assert categories["Pet Food"]["approval_status"] == "pending"
    assert categories["Pet Food"]["can_sell"] is False
    assert item["can_sell"] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "business_status",
    ["draft", "pending", "changes_requested", "suspended", "rejected"],
)
def test_cannot_sell_when_business_is_not_approved(
    api_client, vendor, business_status
):
    business = make_business(
        vendor,
        "Unapproved Shop",
        verification_status=business_status,
    )
    BusinessCategory.objects.create(
        business=business,
        category=make_category("Veterinary"),
        approval_status=BusinessCategory.ApprovalStatus.APPROVED,
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))
    item = find(get_results(response), "Unapproved Shop")

    assert item["categories"][0]["can_sell"] is False
    assert item["can_sell"] is False


@pytest.mark.django_db
def test_cannot_sell_when_business_is_inactive(api_client, vendor):
    business = make_business(
        vendor,
        "Inactive Shop",
        verification_status=Business.VerificationStatus.APPROVED,
        is_active=False,
    )
    BusinessCategory.objects.create(
        business=business,
        category=make_category("Veterinary"),
        approval_status=BusinessCategory.ApprovalStatus.APPROVED,
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))
    item = find(get_results(response), "Inactive Shop")

    assert item["can_sell"] is False


@pytest.mark.django_db
def test_business_without_categories_cannot_sell(api_client, vendor):
    make_business(
        vendor,
        "No Category Shop",
        verification_status=Business.VerificationStatus.APPROVED,
    )
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))
    item = find(get_results(response), "No Category Shop")

    assert item["categories"] == []
    assert item["can_sell"] is False


@pytest.mark.django_db
def test_vendor_without_businesses_gets_an_empty_list(api_client, vendor):
    api_client.force_authenticate(user=vendor)

    response = api_client.get(reverse(URL_NAME))

    assert response.status_code == status.HTTP_200_OK
    assert get_results(response) == []


@pytest.mark.django_db
def test_unauthenticated_user_cannot_see_verification_status(api_client):
    response = api_client.get(reverse(URL_NAME))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["customer", "admin", "system_admin"])
def test_non_vendors_cannot_see_verification_status(
    api_client, request, role_fixture
):
    api_client.force_authenticate(user=request.getfixturevalue(role_fixture))

    response = api_client.get(reverse(URL_NAME))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_verification_status_is_read_only(api_client, vendor):
    api_client.force_authenticate(user=vendor)

    response = api_client.post(reverse(URL_NAME), {}, format="json")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
