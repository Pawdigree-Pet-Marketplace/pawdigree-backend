from rest_framework import permissions
from rest_framework.permissions import BasePermission

from accounts.models import User

ADMIN_ROLES = (User.Role.ADMIN, User.Role.SYSTEM_ADMIN)


class IsCustomer(BasePermission):
    """Allow only authenticated customers."""

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.CUSTOMER
        )


class IsVendor(BasePermission):
    """Allow only authenticated vendors to access vendor-owned resources."""

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.VENDOR
        )


class IsAdmin(BasePermission):
    """Allow admins and superusers to perform account-level admin actions."""

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and (
                user.role in (User.Role.ADMIN, User.Role.SYSTEM_ADMIN)
                or user.is_superuser
            )
        )


class IsSystemAdmin(BasePermission):
    """Allow system admins and superusers to perform account-level admin tasks."""

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and (
                user.role == User.Role.SYSTEM_ADMIN
                or user.is_superuser
            )
        )


class IsSystemAdminRoleOnly(BasePermission):
    """Allow only authenticated users whose role is SYSTEM_ADMIN."""

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.SYSTEM_ADMIN
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow authenticated users to read and admins to modify."""

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        return user.role in ADMIN_ROLES