from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Lower, TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from accounts.models import User
from adoptions.models import AdoptionApplication
from orders.models import Order, OrderItem, VendorOrder
from pets.models import Pet

from .filters import REPORT_TZ

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=16, decimal_places=2)
# One line of an order: price x quantity.
LINE = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=MONEY)

# Items in vendor orders cancelled after payment.
CANCELLED = Q(vendor_order__status=VendorOrder.Status.CANCELLED)

TOP_N = 10


# ---------- small helpers ----------

def money(value):
    """Decimal -> '1234.50'. Strings avoid float rounding in JSON."""
    return str((value or ZERO).quantize(Decimal("0.01")))


def pct(part, whole):
    return round(part * 100 / whole, 1) if whole else 0.0


def kpi(key, label, value, fmt="count"):
    return {"key": key, "label": label, "value": value, "format": fmt}


def col(key, label, fmt="text"):
    return {"key": key, "label": label, "format": fmt}


def section(key, title, columns, rows):
    return {"key": key, "title": title, "columns": columns, "rows": rows}


def finish(report_type, title, filters, summary, sections):
    """Wrap one report in the common shape every consumer relies on."""
    return {
        "report": report_type,
        "title": title,
        "generated_at": timezone.localtime(
            timezone.now(), REPORT_TZ
        ).isoformat(timespec="seconds"),
        "currency": settings.PAYMENT_CURRENCY,
        "filters": filters.as_dict(),
        "summary": summary,
        "sections": sections,
    }


# ---------- trend (time series) ----------

_TRUNC = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}


def _label(value, group_by):
    local = timezone.localtime(value, REPORT_TZ).date()
    return local.strftime("%Y-%m") if group_by == "month" else local.isoformat()


def period_labels(filters):
    """Every bucket in the range, so empty periods show as zero."""
    start, end, group_by = filters.date_from, filters.date_to, filters.group_by
    labels = []
    if group_by == "day":
        current = start
        while current <= end:
            labels.append(current.isoformat())
            current += timedelta(days=1)
    elif group_by == "week":
        current = start - timedelta(days=start.weekday())  # Monday
        while current <= end:
            labels.append(current.isoformat())
            current += timedelta(days=7)
    else:
        current = start.replace(day=1)
        while current <= end:
            labels.append(current.strftime("%Y-%m"))
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return labels


def build_trend(queryset, filters, date_field, aggregates, money_keys=()):
    """One grouped query, then zero-filled to a continuous series."""
    rows = (
        queryset.annotate(
            period=_TRUNC[filters.group_by](date_field, tzinfo=REPORT_TZ)
        )
        .values("period")
        .annotate(**aggregates)
        .order_by("period")
    )
    found = {_label(row["period"], filters.group_by): row for row in rows}
    series = []
    for label in period_labels(filters):
        row = found.get(label)
        item = {"period": label}
        for key in aggregates:
            value = row[key] if row else None
            item[key] = money(value) if key in money_keys else (value or 0)
        series.append(item)
    return series


def _trend_section(rows, columns):
    return section(
        "trend", "Trend", [col("period", "Period")] + columns, rows
    )


# ---------- users ----------

def build_users_report(f):
    users = User.objects.filter(date_joined__gte=f.start, date_joined__lt=f.end)
    if f.role:
        users = users.filter(role=f.role)
    if f.status:
        users = users.filter(status=f.status)

    totals = users.aggregate(
        new_users=Count("id"),
        verified=Count("id", filter=Q(is_email_verified=True)),
        vendors_approved=Count(
            "id", filter=Q(role=User.Role.VENDOR, approved=True)
        ),
        vendors_awaiting=Count(
            "id", filter=Q(role=User.Role.VENDOR, approved=False)
        ),
    )
    # Whole-platform numbers, independent of the date range.
    platform = User.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=User.AccountStatus.ACTIVE)),
    )

    role_labels = dict(User.Role.choices)
    status_labels = dict(User.AccountStatus.choices)
    by_role = [
        {"role": role_labels.get(r["role"], r["role"]), "users": r["n"]}
        for r in users.values("role").annotate(n=Count("id")).order_by("-n")
    ]
    by_status = [
        {"status": status_labels.get(r["status"], r["status"]), "users": r["n"]}
        for r in users.values("status").annotate(n=Count("id")).order_by("-n")
    ]
    trend = build_trend(
        users, f, "date_joined", {"new_users": Count("id")}
    )

    summary = [
        kpi("new_users", "New users", totals["new_users"]),
        kpi("verified", "With verified email", totals["verified"]),
        kpi("vendors_approved", "New vendors approved", totals["vendors_approved"]),
        kpi("vendors_awaiting", "New vendors awaiting approval", totals["vendors_awaiting"]),
        kpi("platform_total", "All users on the platform", platform["total"]),
        kpi("platform_active", "All active users on the platform", platform["active"]),
    ]
    sections = [
        section("by_role", "New users by role",
                [col("role", "Role"), col("users", "Users", "count")], by_role),
        section("by_status", "New users by account status",
                [col("status", "Status"), col("users", "Users", "count")], by_status),
        _trend_section(trend, [col("new_users", "New users", "count")]),
    ]
    return finish("users", "Users report", f, summary, sections)


# ---------- pets ----------

def build_pets_report(f):
    pets = Pet.objects.filter(created_at__gte=f.start, created_at__lt=f.end)
    if f.listing_type:
        pets = pets.filter(listing_type=f.listing_type)
    if f.species:
        pets = pets.filter(species__iexact=f.species)
    if f.status:
        pets = pets.filter(adoption_status=f.status)
    if f.business:
        pets = pets.filter(business_id=f.business)

    S = Pet.AdoptionStatus
    totals = pets.aggregate(
        listings=Count("pk"),
        approved=Count("pk", filter=Q(approved=True)),
        pending=Count("pk", filter=Q(approved=False, rejection_reason="")),
        rejected=Count("pk", filter=Q(approved=False) & ~Q(rejection_reason="")),
        available=Count("pk", filter=Q(adoption_status=S.AVAILABLE)),
        sold=Count("pk", filter=Q(adoption_status=S.SOLD)),
        adopted=Count("pk", filter=Q(adoption_status=S.ADOPTED)),
    )

    applications = AdoptionApplication.objects.filter(
        created_at__gte=f.start, created_at__lt=f.end
    )
    if f.species:
        applications = applications.filter(pet__species__iexact=f.species)
    if f.business:
        applications = applications.filter(pet__business_id=f.business)
    if f.listing_type:
        applications = applications.filter(pet__listing_type=f.listing_type)

    app_labels = dict(AdoptionApplication.Status.choices)
    app_rows = list(
        applications.values("status").annotate(n=Count("pk")).order_by("-n")
    )
    app_counts = {r["status"]: r["n"] for r in app_rows}
    approved = app_counts.get("APPROVED", 0)
    decided = approved + app_counts.get("REJECTED", 0)

    status_labels = dict(Pet.AdoptionStatus.choices)
    type_labels = dict(Pet.ListingType.choices)
    by_status = [
        {"status": status_labels.get(r["adoption_status"], r["adoption_status"]),
         "pets": r["n"]}
        for r in pets.values("adoption_status").annotate(n=Count("pk")).order_by("-n")
    ]
    by_type = [
        {"listing_type": type_labels.get(r["listing_type"], r["listing_type"]),
         "pets": r["n"]}
        for r in pets.values("listing_type").annotate(n=Count("pk")).order_by("-n")
    ]
    by_species = [
        {"species": r["sp"], "pets": r["n"]}
        for r in pets.annotate(sp=Lower("species"))
        .values("sp").annotate(n=Count("pk")).order_by("-n")[:15]
    ]
    trend = build_trend(pets, f, "created_at", {"listings": Count("pk")})

    summary = [
        kpi("listings", "Listings created", totals["listings"]),
        kpi("approved", "Approved", totals["approved"]),
        kpi("pending", "Awaiting review", totals["pending"]),
        kpi("rejected", "Rejected", totals["rejected"]),
        kpi("available", "Currently available", totals["available"]),
        kpi("sold", "Sold", totals["sold"]),
        kpi("adopted", "Adopted", totals["adopted"]),
        kpi("applications", "Adoption applications", sum(app_counts.values())),
        kpi("approval_rate", "Adoption approval rate", pct(approved, decided), "percent"),
    ]
    sections = [
        section("by_status", "Listings by current status",
                [col("status", "Status"), col("pets", "Pets", "count")], by_status),
        section("by_listing_type", "Listings by type",
                [col("listing_type", "Type"), col("pets", "Pets", "count")], by_type),
        section("by_species", "Listings by species",
                [col("species", "Species"), col("pets", "Pets", "count")], by_species),
        section("applications_by_status", "Adoption applications by status",
                [col("status", "Status"), col("n", "Applications", "count")],
                [{"status": app_labels.get(r["status"], r["status"]), "n": r["n"]}
                 for r in app_rows]),
        _trend_section(trend, [col("listings", "Listings created", "count")]),
    ]
    return finish("pets", "Pets report", f, summary, sections)


# ---------- sales (products and pets share one builder) ----------

def _sales_items(kind, f):
    """Items in PAID orders created in range, for one kind of sale."""
    items = OrderItem.objects.filter(
        vendor_order__order__status=Order.Status.PAID,
        vendor_order__order__created_at__gte=f.start,
        vendor_order__order__created_at__lt=f.end,
    )
    if kind == "product":
        items = items.filter(product__isnull=False)
        if f.category:
            items = items.filter(product__category_id=f.category)
    else:
        items = items.filter(pet__isnull=False)
        if f.species:
            items = items.filter(pet__species__iexact=f.species)
    if f.business:
        items = items.filter(vendor_order__business_id=f.business)
    return items


def build_sales_report(kind, f):
    items = _sales_items(kind, f)
    kept = items.exclude(vendor_order__status=VendorOrder.Status.CANCELLED)
    R = VendorOrder.RefundStatus

    t = items.aggregate(
        orders=Count("vendor_order__order", distinct=True, filter=~CANCELLED),
        units=Sum("quantity", filter=~CANCELLED),
        gross=Sum(LINE),
        cancelled=Sum(LINE, filter=CANCELLED),
        refunded=Sum(LINE, filter=Q(vendor_order__refund_status=R.REFUNDED)),
        refund_pending=Sum(LINE, filter=Q(vendor_order__refund_status=R.REQUIRED)),
    )
    gross = t["gross"] or ZERO
    cancelled = t["cancelled"] or ZERO
    net = gross - cancelled
    orders = t["orders"] or 0
    average = (net / orders) if orders else ZERO

    status_labels = dict(VendorOrder.Status.choices)
    by_status = [
        {"status": status_labels.get(r["vendor_order__status"], r["vendor_order__status"]),
         "vendor_orders": r["n"]}
        for r in items.values("vendor_order__status")
        .annotate(n=Count("vendor_order", distinct=True)).order_by("-n")
    ]

    top_vendors = [
        {"vendor": r["vendor"], "units": r["units"], "net_sales": money(r["net_sales"])}
        for r in kept.annotate(vendor=F("vendor_order__business__name"))
        .values("vendor")
        .annotate(units=Sum("quantity"), net_sales=Sum(LINE))
        .order_by("-net_sales")[:TOP_N]
    ]

    trend = build_trend(
        kept, f, "vendor_order__order__created_at",
        {
            "orders": Count("vendor_order__order", distinct=True),
            "units": Sum("quantity"),
            "net_sales": Sum(LINE),
        },
        money_keys=("net_sales",),
    )

    noun = "Products" if kind == "product" else "Pets"
    summary = [
        kpi("orders", "Orders", orders),
        kpi("units", f"{noun} sold", t["units"] or 0),
        kpi("gross_sales", "Gross sales", money(gross), "money"),
        kpi("cancelled", "Cancelled after payment", money(cancelled), "money"),
        kpi("net_sales", "Net sales", money(net), "money"),
        kpi("average_order_value", "Average order value", money(average), "money"),
        kpi("refunded", "Of cancelled: refunded", money(t["refunded"]), "money"),
        kpi("refund_pending", "Of cancelled: refund pending", money(t["refund_pending"]), "money"),
    ]

    # The grouping dimension differs: category for products, species for pets.
    if kind == "product":
        dim = F("product__category__name")
        dim_section = ("by_category", "Sales by category", "category", "Category")
    else:
        dim = Lower("pet__species")
        dim_section = ("by_species", "Sales by species", "category", "Species")
    by_dim = [
        {"category": r["dim"], "units": r["units"], "net_sales": money(r["net_sales"])}
        for r in kept.annotate(dim=dim).values("dim")
        .annotate(units=Sum("quantity"), net_sales=Sum(LINE))
        .order_by("-net_sales")[:15]
    ]

    sections = [
        section(dim_section[0], dim_section[1],
                [col("category", dim_section[3]), col("units", "Units", "count"),
                 col("net_sales", "Net sales", "money")], by_dim),
    ]
    if kind == "product":
        top_products = [
            {"product": r["product__name"], "vendor": r["product__business__name"],
             "units": r["units"], "net_sales": money(r["net_sales"])}
            for r in kept.values("product_id", "product__name", "product__business__name")
            .annotate(units=Sum("quantity"), net_sales=Sum(LINE))
            .order_by("-net_sales")[:TOP_N]
        ]
        sections.append(section(
            "top_products", "Top products",
            [col("product", "Product"), col("vendor", "Vendor"),
             col("units", "Units", "count"), col("net_sales", "Net sales", "money")],
            top_products))
    sections += [
        section("top_vendors", "Top vendors",
                [col("vendor", "Vendor"), col("units", "Units", "count"),
                 col("net_sales", "Net sales", "money")], top_vendors),
        section("by_status", "Fulfilment status",
                [col("status", "Status"), col("vendor_orders", "Vendor orders", "count")],
                by_status),
        _trend_section(trend, [col("orders", "Orders", "count"),
                               col("units", "Units", "count"),
                               col("net_sales", "Net sales", "money")]),
    ]
    title = "Product sales report" if kind == "product" else "Pet sales report"
    key = "product-sales" if kind == "product" else "pet-sales"
    return finish(key, title, f, summary, sections)


# ---------- overview ----------

def _value(report, key):
    return next(k["value"] for k in report["summary"] if k["key"] == key)


def _trend_rows(report):
    return next(s for s in report["sections"] if s["key"] == "trend")["rows"]


def build_overview_report(f):
    users = build_users_report(f)
    pets = build_pets_report(f)
    products = build_sales_report("product", f)
    pet_sales = build_sales_report("pet", f)

    summary = [
        kpi("new_users", "New users", _value(users, "new_users")),
        kpi("listings", "New pet listings", _value(pets, "listings")),
        kpi("applications", "Adoption applications", _value(pets, "applications")),
        kpi("product_orders", "Product orders", _value(products, "orders")),
        kpi("product_net_sales", "Product net sales", _value(products, "net_sales"), "money"),
        kpi("pet_orders", "Pet sale orders", _value(pet_sales, "orders")),
        kpi("pet_net_sales", "Pet net sales", _value(pet_sales, "net_sales"), "money"),
    ]
    # All four trends use the same period labels, so they zip row for row.
    rows = [
        {"period": u["period"], "new_users": u["new_users"],
         "new_listings": p["listings"], "product_sales": pr["net_sales"],
         "pet_sales": ps["net_sales"]}
        for u, p, pr, ps in zip(
            _trend_rows(users), _trend_rows(pets),
            _trend_rows(products), _trend_rows(pet_sales),
        )
    ]
    sections = [_trend_section(rows, [
        col("new_users", "New users", "count"),
        col("new_listings", "New listings", "count"),
        col("product_sales", "Product net sales", "money"),
        col("pet_sales", "Pet net sales", "money"),
    ])]
    return finish("overview", "Platform overview", f, summary, sections)


BUILDERS = {
    "overview": build_overview_report,
    "users": build_users_report,
    "pets": build_pets_report,
    "product-sales": lambda f: build_sales_report("product", f),
    "pet-sales": lambda f: build_sales_report("pet", f),
}