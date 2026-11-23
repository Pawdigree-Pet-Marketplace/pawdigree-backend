from django.urls import URLPattern, URLResolver, get_resolver

from common.permissions import IsAdmin, IsSystemAdminRoleOnly

ADMIN_PREFIX = "api/admin/"

# Booking management endpoints are accessible to ADMIN and SYSTEM_ADMIN.
BOOKING_ADMIN_ROUTES = {
    "api/admin/bookings/",
    "api/admin/bookings/<int:booking_id>/status/",
}


def collect_routes(patterns, prefix=""):
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from collect_routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route, entry.callback


def test_account_management_routes_require_system_admin_role():
    """All /api/admin/ routes that are NOT booking routes must be SYSTEM_ADMIN-only."""
    routes = [
        (route, callback)
        for route, callback in collect_routes(get_resolver().url_patterns)
        if route.startswith(ADMIN_PREFIX) and route not in BOOKING_ADMIN_ROUTES
    ]

    assert len(routes) >= 4, (
        f"Expected at least 4 account-management routes, found {len(routes)}"
    )

    for route, callback in routes:
        view_class = getattr(callback, "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsSystemAdminRoleOnly in view_class.permission_classes, (
            f"{route} must require IsSystemAdminRoleOnly"
        )


def test_booking_admin_routes_require_admin_role():
    """Booking management routes must be accessible to ADMIN and SYSTEM_ADMIN."""
    routes = [
        (route, callback)
        for route, callback in collect_routes(get_resolver().url_patterns)
        if route in BOOKING_ADMIN_ROUTES
    ]

    assert len(routes) == len(BOOKING_ADMIN_ROUTES), (
        f"Expected {len(BOOKING_ADMIN_ROUTES)} booking admin routes, "
        f"found {len(routes)}: {[r for r, _ in routes]}"
    )

    for route, callback in routes:
        view_class = getattr(callback, "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsAdmin in view_class.permission_classes, (
            f"{route} must require IsAdmin"
        )
