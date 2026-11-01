from django.urls import URLPattern, URLResolver, get_resolver

from common.permissions import IsSystemAdminRoleOnly

ADMIN_PREFIX = "api/admin/"


def collect_routes(patterns, prefix=""):
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from collect_routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route, entry.callback


def test_every_admin_route_requires_system_admin_role():
    routes = [
        (route, callback)
        for route, callback in collect_routes(get_resolver().url_patterns)
        if route.startswith(ADMIN_PREFIX)
    ]

    # Guard against passing by checking nothing.
    assert len(routes) >= 4

    for route, callback in routes:
        view_class = getattr(callback, "cls", None)
        assert view_class is not None, f"{route} is not a class-based view"
        assert IsSystemAdminRoleOnly in view_class.permission_classes, route
