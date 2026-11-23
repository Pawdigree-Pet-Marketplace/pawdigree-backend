"""Tests for the admin platform reports.

All report data sits in March 2025 so it never overlaps with the accounts
the tests create "now".
"""
import itertools
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APITestCase
from django.core.management import call_command

from accounts.models import User
from adoptions.models import AdoptionApplication
from audit.models import AuditLog
from businesses.models import Business
from categories.models import Category
from orders.models import Order, OrderItem, VendorOrder
from pets.models import Pet
from products.models import Product

from .filters import REPORT_TZ
from .models import SavedReport

_ids = itertools.count(1)

ALL_REPORTS = (
    "admin-report-overview",
    "admin-report-users",
    "admin-report-pets",
    "admin-report-product-sales",
    "admin-report-pet-sales",
)


# ---------- fixtures ----------

def local(year, month, day, hour=12, minute=0):
    """A moment in the report time zone."""
    return datetime(year, month, day, hour, minute, tzinfo=REPORT_TZ)


def make_user(role, **extra):
    n = next(_ids)
    return User.objects.create_user(
        username=f"{role.lower()}{n}",
        email=f"{role.lower()}{n}@example.com",
        password="Pass12345!",
        role=role,
        **extra,
    )


def make_business(vendor):
    n = next(_ids)
    return Business.objects.create(
        vendor=vendor,
        name=f"Shop {n}",
        description="A shop",
        contact="0700000000",
        email=f"shop{n}@example.com",
        address="1 Main Road",
        city_district="Kampala",
        verification_status=Business.VerificationStatus.APPROVED,
    )


def make_category(kind=Category.Kind.MERCHANDISE):
    return Category.objects.create(name=f"Category {next(_ids)}", kind=kind)


def make_product(business, category, price="100.00"):
    return Product.objects.create(
        business=business,
        category=category,
        name=f"Product {next(_ids)}",
        price=Decimal(price),
        stock_quantity=100,
        approved=True,
    )


def make_pet(vendor, business, when=None, **extra):
    fields = dict(
        vendor=vendor,
        business=business,
        name=f"Pet {next(_ids)}",
        species="dog",
        age=6,
        gender=Pet.Gender.MALE,
        size=Pet.Size.SMALL,
        listing_type=Pet.ListingType.SALE,
        price=Decimal("1000.00"),
        approved=True,
    )
    fields.update(extra)
    pet = Pet.objects.create(**fields)
    if when:
        backdate(pet, when)
    return pet


def backdate(obj, when):
    """created_at is auto-set, so move it with a queryset update."""
    type(obj).objects.filter(pk=obj.pk).update(created_at=when)


def make_order(
    customer,
    lines,
    *,
    status=Order.Status.PAID,
    vendor_status=VendorOrder.Status.PAID,
    refund=VendorOrder.RefundStatus.NONE,
    when=None,
):
    """lines: [(business, product_or_pet, quantity, unit_price), ...].

    One vendor order is made per business, as in real checkouts.
    """
    order = Order.objects.create(customer=customer, status=status)
    vendor_orders = {}
    for business, thing, quantity, price in lines:
        vendor_order = vendor_orders.get(business.pk)
        if vendor_order is None:
            vendor_order = vendor_orders[business.pk] = (
                VendorOrder.objects.create(
                    order=order,
                    business=business,
                    status=vendor_status,
                    refund_status=refund,
                )
            )
        kind = {"pet": thing} if isinstance(thing, Pet) else {"product": thing}
        OrderItem.objects.create(
            vendor_order=vendor_order,
            quantity=quantity,
            unit_price=Decimal(price),
            **kind,
        )
    if when:
        backdate(order, when)
    return order


class ReportTestCase(APITestCase):
    RANGE = {"date_from": "2025-03-01", "date_to": "2025-03-31"}

    def setUp(self):
        self.admin = make_user("ADMIN")
        self.system_admin = make_user("SYSTEM_ADMIN")
        self.customer = make_user("CUSTOMER")
        self.vendor = make_user("VENDOR", approved=True)
        self.business = make_business(self.vendor)
        self.category = make_category()
        self.product = make_product(self.business, self.category)
        self.client.force_authenticate(self.admin)

    def get(self, route, **params):
        return self.client.get(reverse(route), params)

    def report(self, route, **params):
        """GET a report for March 2025 and return its JSON."""
        response = self.get(route, **{**self.RANGE, **params})
        self.assertEqual(response.status_code, 200)
        return response.data

    @staticmethod
    def kpis(report):
        return {item["key"]: item["value"] for item in report["summary"]}

    @staticmethod
    def rows(report, key):
        section = next(s for s in report["sections"] if s["key"] == key)
        return section["rows"]


# ---------- who may call ----------

class PermissionTests(ReportTestCase):
    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        for route in ALL_REPORTS + ("admin-report-saved-list",):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 401)

    def test_customer_and_vendor_get_403(self):
        for user in (self.customer, self.vendor):
            self.client.force_authenticate(user)
            for route in ALL_REPORTS + ("admin-report-saved-list",):
                with self.subTest(user=user.role, route=route):
                    self.assertEqual(self.get(route).status_code, 403)

    def test_admin_and_system_admin_get_200(self):
        for user in (self.admin, self.system_admin):
            self.client.force_authenticate(user)
            for route in ALL_REPORTS:
                with self.subTest(user=user.role, route=route):
                    self.assertEqual(self.get(route).status_code, 200)


# ---------- filter validation ----------

class FilterTests(ReportTestCase):
    def test_defaults_to_the_last_30_days(self):
        data = self.get("admin-report-users").data
        today = timezone.localtime(timezone.now(), REPORT_TZ).date()
        self.assertEqual(data["filters"]["date_to"], today.isoformat())
        self.assertEqual(
            data["filters"]["date_from"],
            (today - timedelta(days=29)).isoformat(),
        )

    def test_only_date_to_given_looks_back_30_days_from_it(self):
        data = self.get("admin-report-users", date_to="2025-03-31").data
        self.assertEqual(data["filters"]["date_from"], "2025-03-02")

    def test_date_from_after_date_to_is_rejected(self):
        response = self.get(
            "admin-report-users", date_from="2025-03-31", date_to="2025-03-01"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_from", response.data)

    def test_range_limit_is_366_days_inclusive(self):
        ok = self.get(
            "admin-report-users", date_from="2024-03-31", date_to="2025-03-31"
        )
        too_long = self.get(
            "admin-report-users", date_from="2024-03-31", date_to="2025-04-01"
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(too_long.status_code, 400)

    def test_bad_values_are_rejected(self):
        for params in (
            {"group_by": "year"},
            {"date_from": "03/01/2025"},
            {"export": "csv"},
            {"business": "not-a-uuid"},
        ):
            with self.subTest(params=params):
                self.assertEqual(
                    self.get("admin-report-users", **params).status_code, 400
                )

    def test_filter_not_supported_by_a_report_is_rejected(self):
        response = self.get("admin-report-users", category=1)
        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)
        self.assertEqual(
            self.get("admin-report-pet-sales", category=1).status_code, 400
        )
        self.assertEqual(
            self.get("admin-report-overview", role="VENDOR").status_code, 400
        )

    def test_status_is_checked_per_report(self):
        self.assertEqual(
            self.get("admin-report-users", status="sold").status_code, 400
        )
        self.assertEqual(
            self.get("admin-report-users", status="active").status_code, 200
        )
        self.assertEqual(
            self.get("admin-report-pets", status="SOLD").status_code, 200
        )
        self.assertEqual(
            self.get("admin-report-pets", status="active").status_code, 400
        )


# ---------- users report ----------

class UsersReportTests(ReportTestCase):
    def test_counts_only_users_who_joined_in_range(self):
        make_user("CUSTOMER", date_joined=local(2025, 3, 5))
        make_user("CUSTOMER", date_joined=local(2025, 3, 6))
        make_user("CUSTOMER", date_joined=local(2025, 2, 20))
        data = self.report("admin-report-users")
        self.assertEqual(self.kpis(data)["new_users"], 2)

    def test_range_edges_use_the_report_time_zone(self):
        make_user("CUSTOMER", date_joined=local(2025, 3, 1, 0, 0))     # in
        make_user("CUSTOMER", date_joined=local(2025, 3, 31, 23, 59))  # in
        make_user("CUSTOMER", date_joined=local(2025, 4, 1, 0, 0))     # out
        make_user("CUSTOMER", date_joined=local(2025, 2, 28, 23, 59))  # out
        data = self.report("admin-report-users")
        self.assertEqual(self.kpis(data)["new_users"], 2)

    def test_role_and_status_filters(self):
        make_user("CUSTOMER", date_joined=local(2025, 3, 5))
        make_user("VENDOR", date_joined=local(2025, 3, 6))
        make_user(
            "CUSTOMER", date_joined=local(2025, 3, 7),
            status=User.AccountStatus.SUSPENDED,
        )
        self.assertEqual(
            self.kpis(self.report("admin-report-users", role="VENDOR"))["new_users"], 1
        )
        self.assertEqual(
            self.kpis(self.report("admin-report-users", status="suspended"))["new_users"], 1
        )

    def test_vendor_approval_and_verification_counts(self):
        make_user("VENDOR", approved=True, date_joined=local(2025, 3, 5))
        make_user("VENDOR", approved=False, date_joined=local(2025, 3, 6))
        make_user("CUSTOMER", is_email_verified=True, date_joined=local(2025, 3, 7))
        k = self.kpis(self.report("admin-report-users"))
        self.assertEqual(k["vendors_approved"], 1)
        self.assertEqual(k["vendors_awaiting"], 1)
        self.assertEqual(k["verified"], 1)

    def test_breakdown_by_role_uses_readable_labels(self):
        make_user("CUSTOMER", date_joined=local(2025, 3, 5))
        make_user("CUSTOMER", date_joined=local(2025, 3, 6))
        make_user("VENDOR", date_joined=local(2025, 3, 7))
        rows = self.rows(self.report("admin-report-users"), "by_role")
        self.assertEqual(
            {r["role"]: r["users"] for r in rows},
            {"Customer": 2, "Vendor": 1},
        )

    def test_platform_totals_ignore_the_date_range(self):
        data = self.report("admin-report-users")
        # The five accounts from setUp joined "now", outside March 2025.
        self.assertEqual(self.kpis(data)["new_users"], 0)
        self.assertEqual(self.kpis(data)["platform_total"], User.objects.count())

    def test_trend_is_zero_filled_for_every_period(self):
        make_user("CUSTOMER", date_joined=local(2025, 3, 5))
        daily = self.rows(self.report("admin-report-users"), "trend")
        self.assertEqual(len(daily), 31)
        by_day = {r["period"]: r["new_users"] for r in daily}
        self.assertEqual(by_day["2025-03-05"], 1)
        self.assertEqual(by_day["2025-03-06"], 0)

        weekly = self.rows(self.report("admin-report-users", group_by="week"), "trend")
        self.assertEqual(
            [r["period"] for r in weekly],
            ["2025-02-24", "2025-03-03", "2025-03-10",
             "2025-03-17", "2025-03-24", "2025-03-31"],
        )
        monthly = self.rows(self.report("admin-report-users", group_by="month"), "trend")
        self.assertEqual([r["period"] for r in monthly], ["2025-03"])
        self.assertEqual(monthly[0]["new_users"], 1)


# ---------- pets report ----------

class PetsReportTests(ReportTestCase):
    def setUp(self):
        super().setUp()
        v, b = self.vendor, self.business
        self.sale_dog = make_pet(v, b, when=local(2025, 3, 5))
        self.adopted_dog = make_pet(
            v, b, when=local(2025, 3, 6),
            listing_type=Pet.ListingType.ADOPTION, price=None,
            adoption_status=Pet.AdoptionStatus.ADOPTED,
        )
        self.rejected_cat = make_pet(
            v, b, when=local(2025, 3, 7), species="Cat",
            approved=False, rejection_reason="Blurry photos",
        )
        self.pending_cat = make_pet(
            v, b, when=local(2025, 3, 8), species="cat",
            listing_type=Pet.ListingType.ADOPTION, price=None, approved=False,
        )
        make_pet(v, b, when=local(2025, 2, 1))  # outside the range

    def test_headline_counts(self):
        k = self.kpis(self.report("admin-report-pets"))
        self.assertEqual(k["listings"], 4)
        self.assertEqual(k["approved"], 2)
        self.assertEqual(k["pending"], 1)
        self.assertEqual(k["rejected"], 1)
        self.assertEqual(k["adopted"], 1)
        self.assertEqual(k["available"], 3)

    def test_filters(self):
        self.assertEqual(
            self.kpis(self.report("admin-report-pets", listing_type="ADOPTION"))["listings"], 2
        )
        # Species matching ignores case ("Cat" and "cat" are the same).
        self.assertEqual(
            self.kpis(self.report("admin-report-pets", species="CAT"))["listings"], 2
        )
        self.assertEqual(
            self.kpis(self.report("admin-report-pets", status="ADOPTED"))["listings"], 1
        )
        other = make_business(make_user("VENDOR"))
        self.assertEqual(
            self.kpis(self.report("admin-report-pets", business=str(other.pk)))["listings"], 0
        )

    def test_species_are_grouped_case_insensitively(self):
        rows = self.rows(self.report("admin-report-pets"), "by_species")
        self.assertEqual({r["species"]: r["pets"] for r in rows}, {"dog": 2, "cat": 2})

    def test_adoption_applications_and_approval_rate(self):
        other = make_user("CUSTOMER")
        specs = (
            (self.customer, self.adopted_dog, "APPROVED"),
            (self.customer, self.pending_cat, "REJECTED"),
            (other, self.pending_cat, "PENDING"),
        )
        for customer, pet, status in specs:
            application = AdoptionApplication.objects.create(
                pet=pet, customer=customer, status=status,
                home_type="HOUSE", previous_pet_experience="SOME",
                message="Please",
            )
            backdate(application, local(2025, 3, 10))
        k = self.kpis(self.report("admin-report-pets"))
        self.assertEqual(k["applications"], 3)
        self.assertEqual(k["approval_rate"], 50.0)  # 1 approved of 2 decided
        rows = self.rows(self.report("admin-report-pets"), "applications_by_status")
        self.assertEqual(sum(r["n"] for r in rows), 3)

    def test_approval_rate_is_zero_when_nothing_was_decided(self):
        self.assertEqual(self.kpis(self.report("admin-report-pets"))["approval_rate"], 0.0)


# ---------- sales reports ----------

class SalesTests(ReportTestCase):
    def setUp(self):
        super().setUp()
        self.pet_a = make_pet(self.vendor, self.business)
        self.pet_b = make_pet(self.vendor, self.business)
        b, p, c = self.business, self.product, self.customer
        cancelled = VendorOrder.Status.CANCELLED
        refund = VendorOrder.RefundStatus

        # Counted: product 200.
        make_order(c, [(b, p, 2, "100.00")], when=local(2025, 3, 10))
        # Counted: a pet for 1000.
        make_order(c, [(b, self.pet_a, 1, "1000.00")], when=local(2025, 3, 11))
        # Counted: one order holding a product (50) AND a pet (800).
        make_order(
            c, [(b, p, 1, "50.00"), (b, self.pet_b, 1, "800.00")],
            when=local(2025, 3, 12),
        )
        # Never paid: must not count.
        make_order(
            c, [(b, p, 5, "100.00")], status=Order.Status.PENDING_PAYMENT,
            vendor_status=VendorOrder.Status.PENDING_PAYMENT,
            when=local(2025, 3, 12),
        )
        make_order(
            c, [(b, p, 5, "100.00")], status=Order.Status.EXPIRED,
            vendor_status=VendorOrder.Status.EXPIRED, when=local(2025, 3, 12),
        )
        # Paid, then cancelled and refunded: 300.
        make_order(
            c, [(b, p, 3, "100.00")], vendor_status=cancelled,
            refund=refund.REFUNDED, when=local(2025, 3, 13),
        )
        # Paid, then cancelled, refund still owed: 100.
        make_order(
            c, [(b, p, 1, "100.00")], vendor_status=cancelled,
            refund=refund.REQUIRED, when=local(2025, 3, 14),
        )
        # Outside the range.
        make_order(c, [(b, p, 9, "100.00")], when=local(2025, 2, 10))

    def test_product_sales_totals_exclude_pets_and_unpaid_orders(self):
        k = self.kpis(self.report("admin-report-product-sales"))
        self.assertEqual(k["orders"], 2)
        self.assertEqual(k["units"], 3)
        self.assertEqual(k["gross_sales"], "650.00")
        self.assertEqual(k["cancelled"], "400.00")
        self.assertEqual(k["net_sales"], "250.00")
        self.assertEqual(k["average_order_value"], "125.00")
        self.assertEqual(k["refunded"], "300.00")
        self.assertEqual(k["refund_pending"], "100.00")

    def test_pet_sales_totals_exclude_products(self):
        k = self.kpis(self.report("admin-report-pet-sales"))
        self.assertEqual(k["orders"], 2)
        self.assertEqual(k["units"], 2)
        self.assertEqual(k["gross_sales"], "1800.00")
        self.assertEqual(k["cancelled"], "0.00")
        self.assertEqual(k["net_sales"], "1800.00")
        self.assertEqual(k["average_order_value"], "900.00")

    def test_money_is_returned_as_strings(self):
        k = self.kpis(self.report("admin-report-product-sales"))
        for key in ("gross_sales", "net_sales", "average_order_value"):
            self.assertIsInstance(k[key], str)

    def test_status_breakdown_counts_only_paid_orders(self):
        rows = self.rows(self.report("admin-report-product-sales"), "by_status")
        self.assertEqual(
            {r["status"]: r["vendor_orders"] for r in rows},
            {"Paid": 2, "Cancelled": 2},
        )

    def test_product_breakdowns(self):
        data = self.report("admin-report-product-sales")
        self.assertEqual(
            self.rows(data, "by_category"),
            [{"category": self.category.name, "units": 3, "net_sales": "250.00"}],
        )
        top = self.rows(data, "top_products")
        self.assertEqual(top[0]["product"], self.product.name)
        self.assertEqual(top[0]["net_sales"], "250.00")

    def test_pet_breakdown_by_species(self):
        rows = self.rows(self.report("admin-report-pet-sales"), "by_species")
        self.assertEqual(
            rows, [{"category": "dog", "units": 2, "net_sales": "1800.00"}]
        )

    def test_category_filter_applies_to_product_sales(self):
        other_category = make_category()
        other_product = make_product(self.business, other_category)
        make_order(
            self.customer, [(self.business, other_product, 1, "70.00")],
            when=local(2025, 3, 15),
        )
        k = self.kpis(self.report(
            "admin-report-product-sales", category=other_category.pk
        ))
        self.assertEqual(k["net_sales"], "70.00")

    def test_business_filter_and_top_vendors_ranking(self):
        shop = make_business(make_user("VENDOR"))
        item = make_product(shop, self.category)
        make_order(
            self.customer, [(shop, item, 1, "999.00")], when=local(2025, 3, 15)
        )
        data = self.report("admin-report-product-sales")
        vendors = self.rows(data, "top_vendors")
        self.assertEqual(vendors[0]["vendor"], shop.name)   # 999 beats 250
        self.assertEqual(vendors[1]["vendor"], self.business.name)

        only = self.report("admin-report-product-sales", business=str(shop.pk))
        self.assertEqual(self.kpis(only)["net_sales"], "999.00")

    def test_species_filter_applies_to_pet_sales(self):
        cat = make_pet(self.vendor, self.business, species="cat")
        make_order(
            self.customer, [(self.business, cat, 1, "300.00")],
            when=local(2025, 3, 16),
        )
        k = self.kpis(self.report("admin-report-pet-sales", species="CAT"))
        self.assertEqual(k["net_sales"], "300.00")

    def test_orders_are_dated_in_the_report_time_zone(self):
        p, b, c = self.product, self.business, self.customer
        make_order(c, [(b, p, 1, "10.00")], when=local(2025, 3, 1, 0, 0))    # in
        make_order(c, [(b, p, 1, "10.00")], when=local(2025, 3, 31, 23, 59)) # in
        make_order(c, [(b, p, 1, "10.00")], when=local(2025, 4, 1, 0, 0))    # out
        make_order(c, [(b, p, 1, "10.00")], when=local(2025, 2, 28, 23, 59)) # out
        k = self.kpis(self.report("admin-report-product-sales"))
        self.assertEqual(k["net_sales"], "270.00")

    def test_trend_adds_up_for_every_grouping(self):
        expected = {"day": 31, "week": 6, "month": 1}
        for group_by, count in expected.items():
            with self.subTest(group_by=group_by):
                rows = self.rows(
                    self.report("admin-report-product-sales", group_by=group_by),
                    "trend",
                )
                self.assertEqual(len(rows), count)
                total = sum(Decimal(r["net_sales"]) for r in rows)
                self.assertEqual(total, Decimal("250.00"))

    def test_an_empty_range_returns_zeros_not_errors(self):
        data = self.get(
            "admin-report-product-sales",
            date_from="2020-01-01", date_to="2020-01-31",
        ).data
        k = self.kpis(data)
        self.assertEqual(k["orders"], 0)
        self.assertEqual(k["net_sales"], "0.00")
        self.assertEqual(k["average_order_value"], "0.00")
        self.assertEqual(self.rows(data, "top_products"), [])

    def test_sales_report_uses_a_constant_number_of_queries(self):
        with CaptureQueriesContext(connection) as queries:
            self.get("admin-report-product-sales", **self.RANGE)
        self.assertLessEqual(len(queries), 12)

    def test_overview_combines_the_other_reports(self):
        data = self.report("admin-report-overview")
        k = self.kpis(data)
        self.assertEqual(k["product_net_sales"], "250.00")
        self.assertEqual(k["pet_net_sales"], "1800.00")
        self.assertEqual(k["product_orders"], 2)
        rows = self.rows(data, "trend")
        self.assertEqual(len(rows), 31)
        self.assertEqual(sum(Decimal(r["product_sales"]) for r in rows), Decimal("250.00"))
        self.assertEqual(sum(Decimal(r["pet_sales"]) for r in rows), Decimal("1800.00"))


# ---------- saved reports ----------

class SavedReportTests(ReportTestCase):
    def setUp(self):
        super().setUp()
        self.pet = make_pet(self.vendor, self.business)
        make_order(
            self.customer, [(self.business, self.pet, 1, "1000.00")],
            when=local(2025, 3, 11),
        )
        self.url = reverse("admin-report-saved-list")

    def save(self, **overrides):
        payload = {
            "name": "March pet sales",
            "report_type": "pet-sales",
            "filters": dict(self.RANGE),
            **overrides,
        }
        return self.client.post(self.url, payload, format="json")

    def detail(self, saved_id):
        return reverse("admin-report-saved-detail", args=[saved_id])

    def test_saving_stores_a_snapshot_and_logs_it(self):
        response = self.save()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["report"], "pet-sales")
        self.assertEqual(response.data["generated_by_email"], self.admin.email)
        saved = SavedReport.objects.get()
        self.assertEqual(saved.generated_by, self.admin)
        entry = AuditLog.objects.get(action="report.saved")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_id, str(saved.pk))

    def test_saved_filters_hold_the_resolved_dates(self):
        response = self.client.post(
            self.url, {"name": "No dates", "report_type": "users"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        filters = response.data["filters"]
        self.assertIn("date_from", filters)
        self.assertIn("date_to", filters)
        self.assertEqual(filters["group_by"], "day")

    def test_a_saved_report_does_not_change_when_data_changes(self):
        saved_id = self.save().data["id"]
        other_pet = make_pet(self.vendor, self.business)
        make_order(
            self.customer, [(self.business, other_pet, 1, "500.00")],
            when=local(2025, 3, 12),
        )
        frozen = self.client.get(self.detail(saved_id)).data["data"]
        self.assertEqual(self.kpis(frozen)["net_sales"], "1000.00")
        live = self.report("admin-report-pet-sales")
        self.assertEqual(self.kpis(live)["net_sales"], "1500.00")

    def test_list_is_light_paginated_and_filterable(self):
        self.save()
        self.save(name="March users", report_type="users")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        for item in response.data["results"]:
            self.assertNotIn("data", item)
        only = self.client.get(self.url, {"report_type": "users"})
        self.assertEqual(only.data["count"], 1)
        bad = self.client.get(self.url, {"report_type": "nonsense"})
        self.assertEqual(bad.status_code, 400)

    def test_invalid_requests_are_rejected_and_nothing_is_saved(self):
        cases = (
            {"report_type": "nonsense"},
            {"name": ""},
            {"filters": {"date_from": "2025-03-31", "date_to": "2025-03-01"}},
            {"filters": {"category": 1}},   # not a pet-sales filter
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.save(**overrides).status_code, 400)
        self.assertEqual(SavedReport.objects.count(), 0)
        self.assertIn("filters", self.save(filters={"category": 1}).data)

    def test_any_admin_can_view_but_customers_cannot(self):
        saved_id = self.save().data["id"]
        self.client.force_authenticate(make_user("ADMIN"))
        self.assertEqual(self.client.get(self.detail(saved_id)).status_code, 200)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get(self.detail(saved_id)).status_code, 403)

    def test_only_the_creator_or_a_system_admin_can_delete(self):
        saved_id = self.save().data["id"]
        self.client.force_authenticate(make_user("ADMIN"))
        self.assertEqual(self.client.delete(self.detail(saved_id)).status_code, 403)
        self.assertTrue(SavedReport.objects.filter(pk=saved_id).exists())

        self.client.force_authenticate(self.system_admin)
        self.assertEqual(self.client.delete(self.detail(saved_id)).status_code, 204)
        self.assertFalse(SavedReport.objects.filter(pk=saved_id).exists())

        entry = AuditLog.objects.get(action="report.deleted")
        self.assertEqual(entry.actor, self.system_admin)
        self.assertEqual(entry.actor_role, "SYSTEM_ADMIN")
        self.assertEqual(entry.details["name"], "March pet sales")
        self.assertEqual(entry.details["saved_by"], self.admin.email)
        self.assertTrue(entry.details["deleted_by_system_admin"])
        
    def test_the_creator_can_delete_their_own_report(self):
        saved_id = self.save().data["id"]
        self.assertEqual(self.client.delete(self.detail(saved_id)).status_code, 204)
        self.assertEqual(self.client.get(self.detail(saved_id)).status_code, 404)
        
    def trash(self):
        return self.client.get(reverse("admin-report-saved-trash"))

    def restore_url(self, saved_id):
        return reverse("admin-report-saved-restore", args=[saved_id])

    def test_delete_moves_the_report_to_the_trash(self):
        saved_id = self.save().data["id"]
        self.assertEqual(self.client.delete(self.detail(saved_id)).status_code, 204)

        self.assertEqual(self.client.get(self.detail(saved_id)).status_code, 404)
        self.assertEqual(self.client.get(self.url).data["count"], 0)
        trash = self.trash()
        self.assertEqual(trash.data["count"], 1)
        item = trash.data["results"][0]
        self.assertEqual(item["deleted_by_email"], self.admin.email)
        self.assertIsNotNone(item["restorable_until"])
        self.assertNotIn("data", item)
        row = SavedReport.all_objects.get(pk=saved_id)   # still in the database
        self.assertIsNotNone(row.deleted_at)

    def test_restore_brings_the_report_back_intact(self):
        saved_id = self.save().data["id"]
        self.client.delete(self.detail(saved_id))

        response = self.client.post(self.restore_url(saved_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.url).data["count"], 1)
        self.assertEqual(self.trash().data["count"], 0)
        restored = self.client.get(self.detail(saved_id)).data["data"]
        self.assertEqual(self.kpis(restored)["net_sales"], "1000.00")
        row = SavedReport.objects.get(pk=saved_id)
        self.assertIsNone(row.deleted_at)
        self.assertIsNone(row.deleted_by)
        self.assertTrue(AuditLog.objects.filter(action="report.restored").exists())

    def test_a_report_deleted_over_30_days_ago_cannot_be_restored(self):
        saved_id = self.save().data["id"]
        self.client.delete(self.detail(saved_id))
        SavedReport.all_objects.filter(pk=saved_id).update(
            deleted_at=timezone.now() - timedelta(days=31)
        )
        self.assertEqual(self.client.post(self.restore_url(saved_id)).status_code, 404)
        self.assertEqual(self.trash().data["count"], 0)

    def test_a_report_deleted_29_days_ago_can_still_be_restored(self):
        saved_id = self.save().data["id"]
        self.client.delete(self.detail(saved_id))
        SavedReport.all_objects.filter(pk=saved_id).update(
            deleted_at=timezone.now() - timedelta(days=29)
        )
        self.assertEqual(self.client.post(self.restore_url(saved_id)).status_code, 200)

    def test_only_the_creator_or_a_system_admin_can_restore(self):
        saved_id = self.save().data["id"]
        self.client.delete(self.detail(saved_id))

        self.client.force_authenticate(make_user("ADMIN"))
        self.assertEqual(self.client.post(self.restore_url(saved_id)).status_code, 403)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(self.restore_url(saved_id)).status_code, 403)
        self.client.force_authenticate(self.system_admin)
        self.assertEqual(self.client.post(self.restore_url(saved_id)).status_code, 200)

    def test_restoring_a_report_that_is_not_deleted_returns_404(self):
        saved_id = self.save().data["id"]
        self.assertEqual(self.client.post(self.restore_url(saved_id)).status_code, 404)

    def test_purge_removes_only_expired_reports(self):
        keep_active = self.save(name="Active").data["id"]
        keep_recent = self.save(name="Recently deleted").data["id"]
        gone = self.save(name="Old deleted").data["id"]
        self.client.delete(self.detail(keep_recent))
        self.client.delete(self.detail(gone))
        SavedReport.all_objects.filter(pk=gone).update(
            deleted_at=timezone.now() - timedelta(days=31)
        )

        call_command("purge_deleted_reports")

        self.assertTrue(SavedReport.all_objects.filter(pk=keep_active).exists())
        self.assertTrue(SavedReport.all_objects.filter(pk=keep_recent).exists())
        self.assertFalse(SavedReport.all_objects.filter(pk=gone).exists())
        entry = AuditLog.objects.get(action="report.purged")
        self.assertEqual(entry.details["name"], "Old deleted")
        self.assertIsNone(entry.actor)    


# ---------- exports ----------

class ExportTests(ReportTestCase):
    def setUp(self):
        super().setUp()
        make_order(
            self.customer, [(self.business, self.product, 2, "50.00")],
            when=local(2025, 3, 10),
        )

    def export(self, route, fmt, **params):
        return self.get(route, **{**self.RANGE, "export": fmt, **params})

    def test_excel_export_has_the_report_data(self):
        response = self.export("admin-report-product-sales", "xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="product-sales_2025-03-01_2025-03-31.xlsx"',
        )
        workbook = load_workbook(BytesIO(response.content))
        self.assertIn("Summary", workbook.sheetnames)
        self.assertIn("Sales by category", workbook.sheetnames)
        summary = workbook["Summary"]
        self.assertEqual(summary["A1"].value, "Product sales report")
        values = {row[0].value: row[1].value for row in summary.iter_rows()}
        # Real numbers, so finance can sum them.
        self.assertEqual(float(values["Net sales"]), 100.0)

    def test_pdf_export(self):
        response = self.export("admin-report-product-sales", "pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_every_report_exports_in_both_formats_even_when_empty(self):
        for route in ALL_REPORTS:
            for fmt in ("xlsx", "pdf"):
                with self.subTest(route=route, fmt=fmt):
                    response = self.get(
                        route, date_from="2020-01-01", date_to="2020-01-31",
                        export=fmt,
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertGreater(len(response.content), 100)

    def test_unknown_format_is_rejected(self):
        self.assertEqual(
            self.export("admin-report-users", "csv").status_code, 400
        )

    def test_exports_are_audited(self):
        self.export("admin-report-users", "pdf")
        entry = AuditLog.objects.get(action="report.exported")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.details["format"], "pdf")
        self.assertEqual(entry.details["report_type"], "users")

    def test_saved_report_export_uses_the_report_name(self):
        saved = self.client.post(
            reverse("admin-report-saved-list"),
            {"name": "March Sales!", "report_type": "product-sales",
             "filters": dict(self.RANGE)},
            format="json",
        ).data
        response = self.client.get(
            reverse("admin-report-saved-detail", args=[saved["id"]]),
            {"export": "xlsx"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="march-sales.xlsx"', response["Content-Disposition"])
        entry = AuditLog.objects.get(action="report.exported")
        self.assertTrue(entry.details["saved_report"])

    def test_saved_report_rejects_an_unknown_format(self):
        saved = self.client.post(
            reverse("admin-report-saved-list"),
            {"name": "x", "report_type": "users"}, format="json",
        ).data
        response = self.client.get(
            reverse("admin-report-saved-detail", args=[saved["id"]]),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 400)