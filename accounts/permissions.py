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
    # Admins and system admins can perform admin-level actions.
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.role in ('ADMIN', 'SYSTEM_ADMIN')
                or user.is_superuser
            )
        )


class IsSystemAdmin(BasePermission):
    # Only system admins can create admin accounts.
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.role == 'SYSTEM_ADMIN' or user.is_superuser)
        )