import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business, BusinessCategory
from categories.models import Category
from services.models import Service

PASSWORD = "StrongPass123!"
Status = Business.VerificationStatus
Approval = BusinessCategory.ApprovalStatus


def make_business(
    vendor,
    verification_status=Status.APPROVED,
    business_type=Business.BusinessType.SERVICE_PROVIDER,
):
    return Business.objects.create(
        vendor=vendor,
        name="Happy Paws",
        description="Pets",
        contact="+256700000000",
        email="shop@example.com",
        address="Plot 1",
        city_district="Kampala",
        verification_status=verification_status,
        business_type=business_type,
    )


def service_payload(business, category=None, **overrides):
    data = {
        "business": business.pk,
        "name": "Dog grooming",
        "service_type": "grooming",
        "description": "Bath and trim",
        "price": "30000.00",
        "duration": 60,
    }
    if category is not None:
        data["category"] = category.pk
    data.update(overrides)
    return data


@pytest.fixture
def vendor(db):
    return User.objects.create_user(
        username="vendor",
        email="vendor@example.com",
        password=PASSWORD,
        role=User.Role.VENDOR,
        is_email_verified=True,
    )


@pytest.fixture
def client(vendor):
    api_client = APIClient()
    api_client.force_authenticate(vendor)
    return api_client


@pytest.fixture
def grooming(db):
    return Category.objects.create(kind=Category.Kind.SERVICES, name="Grooming")


@pytest.fixture
def boarding(db):
    return Category.objects.create(kind=Category.Kind.SERVICES, name="Boarding")


def test_new_category_creates_pending_request_and_keeps_business_approved(
    client, vendor, grooming
):
    business = make_business(vendor)

    response = client.post(
        reverse("service-create"),
        service_payload(business, grooming),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["category"] == grooming.pk
    assert response.data["category_status"] == Approval.PENDING

    link = BusinessCategory.objects.get(business=business, category=grooming)
    assert link.approval_status == Approval.PENDING

    business.refresh_from_db()
    assert business.verification_status == Status.APPROVED


def test_approved_category_is_reused_not_duplicated(client, vendor, grooming):
    business = make_business(vendor)
    BusinessCategory.objects.create(
                kind=Category.Kind.SERVICES,
        business=business,
        category=grooming,
        approval_status=Approval.APPROVED,
    )

    response = client.post(
        reverse("service-create"),
        service_payload(business, grooming),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["category_status"] == Approval.APPROVED
    assert BusinessCategory.objects.filter(business=business).count() == 1


def test_category_is_required_when_creating(client, vendor):
    business = make_business(vendor)

    response = client.post(
        reverse("service-create"),
        service_payload(business),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data
    assert not Service.objects.exists()


def test_rejected_category_is_blocked(client, vendor, grooming):
    business = make_business(vendor)
    BusinessCategory.objects.create(
                kind=Category.Kind.SERVICES,
        business=business,
        category=grooming,
        approval_status=Approval.REJECTED,
    )

    response = client.post(
        reverse("service-create"),
        service_payload(business, grooming),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data
    assert not Service.objects.exists()


def test_suspended_business_cannot_request_a_new_category(
    client, vendor, grooming
):
    business = make_business(vendor, Status.SUSPENDED)

    response = client.post(
        reverse("service-create"),
        service_payload(business, grooming),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not BusinessCategory.objects.filter(business=business).exists()


def test_inactive_category_is_rejected(client, vendor):
    business = make_business(vendor)
    inactive = Category.objects.create(kind=Category.Kind.SERVICES, name="Retired", is_active=False)

    response = client.post(
        reverse("service-create"),
        service_payload(business, inactive),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data


def test_edit_without_category_keeps_the_existing_one(
    client, vendor, grooming
):
    business = make_business(vendor)
    service = Service.objects.create(
        business=business,
        category=grooming,
        name="Dog grooming",
        service_type="grooming",
        description="Bath and trim",
        price="30000.00",
        duration=60,
    )

    response = client.patch(
        reverse("service-detail", args=[service.pk]),
        {"price": "35000.00"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    service.refresh_from_db()
    assert service.category == grooming


def test_edit_to_a_new_category_requests_it(
    client, vendor, grooming, boarding
):
    business = make_business(vendor)
    service = Service.objects.create(
        business=business,
        category=grooming,
        name="Dog grooming",
        service_type="grooming",
        description="Bath and trim",
        price="30000.00",
        duration=60,
    )

    response = client.patch(
        reverse("service-detail", args=[service.pk]),
        {"category": boarding.pk},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    link = BusinessCategory.objects.get(business=business, category=boarding)
    assert link.approval_status == Approval.PENDING

def test_pending_business_cannot_add_services(client, vendor, grooming):
    business = make_business(vendor, verification_status=Status.PENDING)

    response = client.post(
        reverse("service-create"),
        service_payload(business, grooming),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "business" in response.data


def test_merchandise_business_cannot_add_services(client, vendor, grooming):
    business = make_business(
        vendor, business_type=Business.BusinessType.PRODUCT_SELLER
    )

    response = client.post(
        reverse("service-create"),
        service_payload(business, grooming),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "business" in response.data
