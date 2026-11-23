
from django.urls import URLPattern, URLResolver, get_resolver

from common.permissions import IsAdmin, IsSystemAdminRoleOnly

ADMIN_PREFIX = "api/admin/"
# Platform reports are open to both ADMIN and SYSTEM_ADMIN on purpose.
SHARED_ADMIN_APPS = ("admin_reports.",)

SYSTEM_ADMIN_ROUTES = {
    "api/admin/platform-reports/overview/",
    "api/admin/platform-reports/users/",
    "api/admin/platform-reports/pets/",
    "api/admin/platform-reports/product-sales/",
    "api/admin/platform-reports/pet-sales/",
}

ADMIN_ROUTES = {
    "api/admin/platform-reports/saved/",
    "api/admin/platform-reports/saved/<int:pk>/",
    "api/admin/platform-reports/saved/trash/",
    "api/admin/platform-reports/saved/<int:pk>/restore/",
}


def collect_routes(patterns, prefix=""):
    for entry in patterns:
        route = prefix + str(entry.pattern)

        if isinstance(entry, URLResolver):
            yield from collect_routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route, entry.callback


def is_shared_admin_view(callback):
    view_class = getattr(callback, "cls", None)
    return view_class is not None and view_class.__module__.startswith(
        SHARED_ADMIN_APPS
    )


def test_every_admin_route_requires_system_admin_role():
    routes = [
        (route, callback)
        for route, callback in collect_routes(get_resolver().url_patterns)
        if route.startswith(ADMIN_PREFIX) and not is_shared_admin_view(callback)
    ]

    # Guard against passing by checking nothing.
    assert len(routes) >= 4

    # Ensure all expected report routes are registered.
    assert SYSTEM_ADMIN_ROUTES.issubset(routes.keys())
    assert ADMIN_ROUTES.issubset(routes.keys())

    for route, callback in routes.items():
        view_class = getattr(callback, "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsSystemAdminRoleOnly in view_class.permission_classes, route


def test_platform_reports_routes_are_admin_only():
    routes = [
        (route, callback)
        for route, callback in collect_routes(get_resolver().url_patterns)
        if is_shared_admin_view(callback)
    ]

    assert len(routes) >= 5

    for route, callback in routes:
        view_class = callback.cls
        assert IsAdmin in view_class.permission_classes, route
