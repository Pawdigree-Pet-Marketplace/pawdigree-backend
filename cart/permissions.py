from rest_framework.permissions import BasePermission

from accounts.models import User


class IsCustomerOrGuest(BasePermission):
    """Visitors who are not logged in and customers may use the cart. But a  logged-in vendor or admin may not."""

    message = "Only customers and guests can use the cart."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return True
        return user.role == User.Role.CUSTOMER