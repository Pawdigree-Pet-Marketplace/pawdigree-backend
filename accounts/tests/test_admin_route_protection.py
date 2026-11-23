
from django.urls import URLPattern, URLResolver, get_resolver

from common.permissions import IsAdmin, IsSystemAdmin

ADMIN_PREFIX = "api/admin/"

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


def test_every_admin_route_has_the_correct_permission():
    routes = {
        route: callback
        for route, callback in collect_routes(get_resolver().url_patterns)
        if route.startswith(ADMIN_PREFIX)
    }

    # Guard against passing by checking nothing.
    assert len(routes) >= 4

    # Ensure all expected report routes are registered.
    assert SYSTEM_ADMIN_ROUTES.issubset(routes.keys())
    assert ADMIN_ROUTES.issubset(routes.keys())

    for route, callback in routes.items():
        view_class = getattr(callback, "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"

        if route in SYSTEM_ADMIN_ROUTES:
            assert IsSystemAdmin in view_class.permission_classes, route

        elif route in ADMIN_ROUTES:
            assert IsAdmin in view_class.permission_classes, route
