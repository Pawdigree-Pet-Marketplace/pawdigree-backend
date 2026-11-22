"""Aggregation services for administrator dashboard metrics."""

from django.db.models import Count, Q

from accounts.models import User
from bookings.models import Booking
from businesses.models import Business
from orders.models import Order
from pets.models import Pet
from products.models import Product
from reports.models import Report
from services.models import Service


def get_dashboard_summary():
    """Return scalar counts for administrator dashboard overview cards."""
    user_counts = User.objects.aggregate(
        total=Count("pk"),
        customers=Count(
            "pk",
            filter=Q(role=User.Role.CUSTOMER),
        ),
        vendors=Count(
            "pk",
            filter=Q(role=User.Role.VENDOR),
        ),
    )

    pet_count = Pet.objects.count()
    product_count = Product.objects.count()
    service_count = Service.objects.count()

    return {
        "users": user_counts["total"],
        "customers": user_counts["customers"],
        "vendors": user_counts["vendors"],
        "businesses": Business.objects.count(),
        "listings": pet_count + product_count + service_count,
        "bookings": Booking.objects.count(),
        "orders": Order.objects.count(),
        "reports": Report.objects.count(),
    }


def _listing_metrics(queryset):
    """Count listing review and activity states using existing model rules."""
    counts = queryset.aggregate(
        total_count=Count("pk"),
        approved_count=Count("pk", filter=Q(approved=True)),
        # This matches Pet, Product and Service pending_review() querysets.
        pending_count=Count(
            "pk",
            filter=Q(
                approved=False,
                is_active=True,
                rejection_reason="",
            ),
        ),
        # The listing reject actions set a reason while leaving approved false.
        rejected_count=Count(
            "pk",
            filter=Q(approved=False) & ~Q(rejection_reason=""),
        ),
        active_count=Count("pk", filter=Q(is_active=True)),
        inactive_count=Count("pk", filter=Q(is_active=False)),
    )
    return {
        "total": counts["total_count"],
        "approval": {
            "approved": counts["approved_count"],
            "pending": counts["pending_count"],
            "rejected": counts["rejected_count"],
        },
        "active": counts["active_count"],
        "inactive": counts["inactive_count"],
    }


def _choice_counts(queryset, field_name, choices):
    """Return a total and zero-filled counts for one choice field."""
    counts = {value: 0 for value, _label in choices}
    total = 0

    rows = queryset.values(field_name).annotate(count=Count("pk"))
    for row in rows:
        count = row["count"]
        total += count
        value = row[field_name]
        if value in counts:
            counts[value] = count

    return {"total": total, "by_" + field_name: counts}


def _grouped_choice_counts(queryset, dimensions):
    """Count several choice dimensions in one grouped database query."""
    counts_by_dimension = {
        dimension: {value: 0 for value, _label in choices}
        for dimension, choices in dimensions.items()
    }
    total = 0

    rows = queryset.values(*dimensions).annotate(count=Count("pk"))
    for row in rows:
        count = row["count"]
        total += count
        for dimension, counts in counts_by_dimension.items():
            value = row[dimension]
            if value in counts:
                counts[value] += count

    return {
        "total": total,
        **{
            "by_" + dimension: counts
            for dimension, counts in counts_by_dimension.items()
        },
    }


def get_dashboard_statistics():
    """Return status and type breakdowns for dashboard charts and tables.

    Each breakdown uses database grouping or conditional aggregation; rows are
    never loaded individually into Python. Choice buckets come from the models
    so statuses with no records still appear as zero.
    """
    user_by_role = {value: 0 for value, _label in User.Role.choices}
    user_by_status = {
        value: 0 for value, _label in User.AccountStatus.choices
    }
    vendor_by_status = {
        value: 0 for value, _label in User.AccountStatus.choices
    }
    user_total = 0
    vendor_total = 0

    user_rows = User.objects.values("role", "status").annotate(
        count=Count("pk")
    )
    for row in user_rows:
        role = row["role"]
        account_status = row["status"]
        count = row["count"]
        user_total += count
        if role in user_by_role:
            user_by_role[role] += count
        if role == User.Role.VENDOR:
            vendor_total += count
        if account_status in user_by_status:
            user_by_status[account_status] += count
        if role == User.Role.VENDOR and account_status in vendor_by_status:
            vendor_by_status[account_status] += count

    business_by_status = {
        value: 0 for value, _label in Business.VerificationStatus.choices
    }
    business_by_active_state = {"active": 0, "inactive": 0}
    business_total = 0
    business_rows = Business.objects.values(
        "verification_status", "is_active"
    ).annotate(count=Count("pk"))
    for row in business_rows:
        count = row["count"]
        business_total += count
        verification_status = row["verification_status"]
        if verification_status in business_by_status:
            business_by_status[verification_status] += count
        active_state = "active" if row["is_active"] else "inactive"
        business_by_active_state[active_state] += count

    listings_by_type = {
        "pets": _listing_metrics(Pet.objects.all()),
        "products": _listing_metrics(Product.objects.all()),
        "services": _listing_metrics(Service.objects.all()),
    }

    booking_counts = _choice_counts(
        Booking.objects.all(),
        "status",
        Booking.Status.choices,
    )
    order_counts = _choice_counts(
        Order.objects.all(),
        "status",
        Order.Status.choices,
    )
    report_counts = _grouped_choice_counts(
        Report.objects.all(),
        {
            "status": Report.Status.choices,
            "reason": Report.Reason.choices,
        },
    )

    return {
        "users": {
            "total": user_total,
            "by_role": user_by_role,
            "by_status": user_by_status,
        },
        "vendors": {
            "total": vendor_total,
            "by_status": vendor_by_status,
        },
        "businesses": {
            "total": business_total,
            "by_verification_status": business_by_status,
            "by_active_state": business_by_active_state,
        },
        "listings": {
            "total": sum(
                metrics["total"] for metrics in listings_by_type.values()
            ),
            "by_type": listings_by_type,
        },
        "bookings": booking_counts,
        "orders": order_counts,
        "reports": {
            "total": report_counts["total"],
            "by_status": report_counts["by_status"],
            "by_reason": report_counts["by_reason"],
        },
    }
