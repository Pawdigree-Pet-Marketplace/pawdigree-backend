from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import User
from bookings.models import Booking
from businesses.models import Business
from categories.models import Category
from orders.models import Order, VendorOrder
from pets.models import Pet
from products.models import Product
from reports.models import Report
from services.models import Service


SUMMARY_URL = "admin-dashboard-summary"
STATISTICS_URL = "admin-dashboard-statistics"


def make_user(role, suffix, **extra_fields):
    return User.objects.create_user(
        username=f"dashboard_{suffix}",
        email=f"dashboard_{suffix}@example.com",
        password="TestPassword123!",
        role=role,
        **extra_fields,
    )


def make_business(vendor, name, **overrides):
    values = {
        "vendor": vendor,
        "name": name,
        "description": "Dashboard test business",
        "contact": "+256700000001",
        "email": f"{name.lower().replace(' ', '.')}@example.com",
        "address": "Kampala",
        "city_district": "Central",
        "verification_status": Business.VerificationStatus.APPROVED,
    }
    values.update(overrides)
    return Business.objects.create(**values)


@pytest.fixture
def dashboard_records(db):
    """Create a varied, valid set of records for dashboard aggregations."""
    customer = make_user(User.Role.CUSTOMER, "customer")
    vendor = make_user(User.Role.VENDOR, "vendor")
    second_vendor = make_user(User.Role.VENDOR, "second_vendor")

    business = make_business(vendor, "Dashboard Business")
    second_business = make_business(vendor, "Second Dashboard Business")
    other_vendor_business = make_business(second_vendor, "Other Vendor Business")
    inactive_business = make_business(
        second_vendor,
        "Inactive Dashboard Business",
        verification_status=Business.VerificationStatus.PENDING,
        is_active=False,
    )

    merchandise_category = Category.objects.create(
        name="Dashboard Merchandise",
        kind=Category.Kind.MERCHANDISE,
    )

    # Each listing model has approved, pending, rejected and inactive examples.
    pet_states = [
        {"approved": True},
        {"approved": False},
        {"approved": False, "rejection_reason": "Needs correction"},
        {"approved": False, "is_active": False},
    ]
    for index, state in enumerate(pet_states):
        Pet.objects.create(
            vendor=vendor,
            business=business,
            name=f"Dashboard Pet {index}",
            age=12,
            gender=Pet.Gender.UNKNOWN,
            size=Pet.Size.MEDIUM,
            **state,
        )

    product_states = [
        {"approved": True},
        {"approved": False},
        {"approved": False, "rejection_reason": "Incorrect details"},
        {"approved": False, "is_active": False},
    ]
    for index, state in enumerate(product_states):
        Product.objects.create(
            business=business,
            category=merchandise_category,
            name=f"Dashboard Product {index}",
            price=Decimal("10.00"),
            **state,
        )

    service_states = [
        {"approved": True},
        {"approved": False},
        {"approved": False, "rejection_reason": "Incomplete profile"},
        {"approved": False, "is_active": False},
    ]
    for index, state in enumerate(service_states):
        Service.objects.create(
            business=business,
            name=f"Dashboard Service {index}",
            service_type="Grooming",
            description="Dashboard test service",
            price=Decimal("25.00"),
            duration=60,
            **state,
        )

    start_at = timezone.now() + timedelta(days=2)
    for index, (booking_status, _label) in enumerate(Booking.Status.choices):
        Booking.objects.create(
            customer=customer,
            service=Service.objects.filter(business=business).first(),
            start_at=start_at + timedelta(hours=index * 2),
            end_at=start_at + timedelta(hours=index * 2 + 1),
            status=booking_status,
        )

    order = Order.objects.create(customer=customer, status=Order.Status.PAID)
    VendorOrder.objects.create(order=order, business=business)
    VendorOrder.objects.create(order=order, business=second_business)

    report = Report.objects.create(
        reporter=customer,
        reason=Report.Reason.OTHER,
        description="Dashboard report",
        reported_item_type=Report.ReportedItemType.GENERAL,
    )
    return {
        "customer": customer,
        "vendor": vendor,
        "second_vendor": second_vendor,
        "business": business,
        "second_business": second_business,
        "other_vendor_business": other_vendor_business,
        "inactive_business": inactive_business,
        "order": order,
        "report": report,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", [SUMMARY_URL, STATISTICS_URL])
def test_dashboard_endpoints_require_authentication(api_client, url_name):
    response = api_client.get(reverse(url_name))

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", [SUMMARY_URL, STATISTICS_URL])
@pytest.mark.parametrize("role", [User.Role.CUSTOMER, User.Role.VENDOR])
def test_dashboard_endpoints_deny_customers_and_vendors(
    api_client, url_name, role
):
    user = make_user(role, f"denied_{role.lower()}")
    api_client.force_authenticate(user=user)

    response = api_client.get(reverse(url_name))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.SYSTEM_ADMIN])
@pytest.mark.parametrize("url_name", [SUMMARY_URL, STATISTICS_URL])
def test_dashboard_endpoints_allow_administrators(api_client, role, url_name):
    user = make_user(role, f"allowed_{role.lower()}")
    api_client.force_authenticate(user=user)

    response = api_client.get(reverse(url_name))

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.data, dict)


@pytest.mark.django_db
def test_superuser_can_access_dashboard_with_non_admin_role(api_client):
    superuser = make_user(
        User.Role.CUSTOMER,
        "customer_superuser",
        is_staff=True,
        is_superuser=True,
    )
    api_client.force_authenticate(user=superuser)

    response = api_client.get(reverse(STATISTICS_URL))

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_dashboard_statistics_count_nonzero_user_account_statuses(api_client):
    make_user(User.Role.CUSTOMER, "status_active_customer")
    make_user(User.Role.VENDOR, "status_active_vendor")
    make_user(
        User.Role.VENDOR,
        "status_deactivated_vendor",
        status=User.AccountStatus.DEACTIVATED,
        is_active=False,
    )
    make_user(
        User.Role.VENDOR,
        "status_suspended_vendor",
        status=User.AccountStatus.SUSPENDED,
        is_active=False,
    )
    make_user(
        User.Role.CUSTOMER,
        "status_suspended_customer",
        status=User.AccountStatus.SUSPENDED,
        is_active=False,
    )
    admin = make_user(User.Role.ADMIN, "status_reader")
    api_client.force_authenticate(user=admin)

    response = api_client.get(reverse(STATISTICS_URL))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["users"]["by_status"] == {
        User.AccountStatus.ACTIVE: 3,
        User.AccountStatus.DEACTIVATED: 1,
        User.AccountStatus.SUSPENDED: 2,
    }
    assert response.data["vendors"]["by_status"] == {
        User.AccountStatus.ACTIVE: 1,
        User.AccountStatus.DEACTIVATED: 1,
        User.AccountStatus.SUSPENDED: 1,
    }


@pytest.mark.django_db
def test_empty_dashboard_statistics_include_zero_choice_buckets(
    api_client, admin
):
    api_client.force_authenticate(user=admin)

    summary = api_client.get(reverse(SUMMARY_URL))
    statistics = api_client.get(reverse(STATISTICS_URL))

    assert summary.status_code == status.HTTP_200_OK
    assert summary.data == {
        "users": 1,
        "customers": 0,
        "vendors": 0,
        "businesses": 0,
        "listings": 0,
        "bookings": 0,
        "orders": 0,
        "reports": 0,
    }
    assert statistics.status_code == status.HTTP_200_OK
    assert statistics.data["bookings"] == {
        "total": 0,
        "by_status": {value: 0 for value, _ in Booking.Status.choices},
    }
    assert statistics.data["orders"] == {
        "total": 0,
        "by_status": {value: 0 for value, _ in Order.Status.choices},
    }
    assert statistics.data["reports"] == {
        "total": 0,
        "by_status": {value: 0 for value, _ in Report.Status.choices},
        "by_reason": {value: 0 for value, _ in Report.Reason.choices},
    }
    assert statistics.data["listings"]["total"] == 0


@pytest.mark.django_db
def test_dashboard_summary_counts_users_businesses_listings_and_parent_orders(
    api_client, admin, dashboard_records
):
    api_client.force_authenticate(user=admin)

    response = api_client.get(reverse(SUMMARY_URL))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {
        "users": 4,
        "customers": 1,
        "vendors": 2,
        "businesses": 4,
        "listings": 12,
        "bookings": len(Booking.Status.choices),
        "orders": 1,
        "reports": 1,
    }
    assert dashboard_records["order"].vendor_orders.count() == 2


@pytest.mark.django_db
def test_dashboard_statistics_break_down_all_supported_categories(
    api_client, admin, dashboard_records
):
    api_client.force_authenticate(user=admin)

    response = api_client.get(reverse(STATISTICS_URL))

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["users"] == {
        "total": 4,
        "by_role": {
            User.Role.CUSTOMER: 1,
            User.Role.VENDOR: 2,
            User.Role.ADMIN: 1,
            User.Role.SYSTEM_ADMIN: 0,
        },
        "by_status": {
            User.AccountStatus.ACTIVE: 4,
            User.AccountStatus.DEACTIVATED: 0,
            User.AccountStatus.SUSPENDED: 0,
        },
    }
    assert data["vendors"] == {
        "total": 2,
        "by_status": {
            User.AccountStatus.ACTIVE: 2,
            User.AccountStatus.DEACTIVATED: 0,
            User.AccountStatus.SUSPENDED: 0,
        },
    }

    assert data["businesses"]["total"] == 4
    assert data["businesses"]["by_verification_status"] == {
        value: (
            3
            if value == Business.VerificationStatus.APPROVED
            else 1
            if value == Business.VerificationStatus.PENDING
            else 0
        )
        for value, _ in Business.VerificationStatus.choices
    }
    assert data["businesses"]["by_active_state"] == {
        "active": 3,
        "inactive": 1,
    }

    assert data["listings"]["total"] == 12
    assert data["listings"]["by_type"] == {
        kind: {
            "total": 4,
            "approval": {"approved": 1, "pending": 1, "rejected": 1},
            "active": 3,
            "inactive": 1,
        }
        for kind in ("pets", "products", "services")
    }
    assert data["bookings"] == {
        "total": len(Booking.Status.choices),
        "by_status": {value: 1 for value, _ in Booking.Status.choices},
    }
    assert data["orders"] == {
        "total": 1,
        "by_status": {
            value: (1 if value == Order.Status.PAID else 0)
            for value, _ in Order.Status.choices
        },
    }
    assert data["reports"] == {
        "total": 1,
        "by_status": {
            value: (1 if value == Report.Status.PENDING else 0)
            for value, _ in Report.Status.choices
        },
        "by_reason": {
            value: (1 if value == Report.Reason.OTHER else 0)
            for value, _ in Report.Reason.choices
        },
    }
