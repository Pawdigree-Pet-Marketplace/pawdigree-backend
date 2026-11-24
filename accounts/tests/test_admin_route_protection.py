from django.urls import URLPattern, URLResolver, get_resolver

from common.permissions import IsAdmin, IsSystemAdminRoleOnly

ADMIN_PREFIX = "api/admin/"
REPORTS_PREFIX = "api/platform-reports/"

BOOKING_ADMIN_ROUTES = {
    "api/admin/bookings/",
    "api/admin/bookings/<int:booking_id>/status/",
}

LIVE_REPORT_ROUTES = {
    f"{REPORTS_PREFIX}overview/",
    f"{REPORTS_PREFIX}users/",
    f"{REPORTS_PREFIX}pets/",
    f"{REPORTS_PREFIX}product-sales/",
    f"{REPORTS_PREFIX}pet-sales/",
}

SAVED_REPORT_ROUTES = {
    f"{REPORTS_PREFIX}saved/",
    f"{REPORTS_PREFIX}saved/trash/",
    f"{REPORTS_PREFIX}saved/<int:pk>/",
    f"{REPORTS_PREFIX}saved/<int:pk>/restore/",
}

REPORT_ROUTES = LIVE_REPORT_ROUTES | SAVED_REPORT_ROUTES


def collect_routes(patterns, prefix=""):
    for entry in patterns:
        route = prefix + str(entry.pattern)

        if isinstance(entry, URLResolver):
            yield from collect_routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route, entry.callback


def test_account_management_routes_require_system_admin_role():
    all_routes = dict(collect_routes(get_resolver().url_patterns))

    routes = [
        (route, callback)
        for route, callback in all_routes.items()
        if route.startswith(ADMIN_PREFIX) and route not in BOOKING_ADMIN_ROUTES
    ]

    assert len(routes) >= 4, (
        f"Expected at least 4 account-management routes, found {len(routes)}"
    )

    for route, callback in routes:
        view_class = getattr(callback, "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsSystemAdminRoleOnly in view_class.permission_classes, route


def test_booking_admin_routes_require_admin_role():
    all_routes = dict(collect_routes(get_resolver().url_patterns))

    assert BOOKING_ADMIN_ROUTES.issubset(all_routes.keys())

    for route in BOOKING_ADMIN_ROUTES:
        view_class = getattr(all_routes[route], "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsAdmin in view_class.permission_classes, route


def test_live_platform_report_routes_require_admin():
    all_routes = dict(collect_routes(get_resolver().url_patterns))

    assert LIVE_REPORT_ROUTES.issubset(all_routes.keys())

    for route in LIVE_REPORT_ROUTES:
        view_class = getattr(all_routes[route], "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsAdmin in view_class.permission_classes, route


def test_saved_platform_report_routes_require_admin():
    all_routes = dict(collect_routes(get_resolver().url_patterns))

    assert SAVED_REPORT_ROUTES.issubset(all_routes.keys())

    for route in SAVED_REPORT_ROUTES:
        view_class = getattr(all_routes[route], "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsAdmin in view_class.permission_classes, route
