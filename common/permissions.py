from rest_framework import permissions

from accounts.models import User


class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow authenticated users to read and admins to modify."""

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        return user.role == User.Role.ADMIN


class IsVendor(permissions.BasePermission):
    """Allow only authenticated vendors to access business endpoints."""

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.VENDOR
        )