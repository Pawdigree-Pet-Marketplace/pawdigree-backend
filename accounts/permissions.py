from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'CUSTOMER'
        )


class IsVendor(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'VENDOR'
        )


class IsAdmin(BasePermission):
    # Checks that the user is authenticated and has the 'ADMIN' role.
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'ADMIN'
        )


class IsSystemAdmin(BasePermission):
    # Only the system admin (a Django superuser) passes this check.
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )