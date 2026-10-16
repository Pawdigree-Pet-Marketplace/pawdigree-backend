"""Compatibility exports for account-level permissions.

The canonical shared definitions live in common.permissions so the backend uses
one permission source of truth while keeping import compatibility for older
account imports.
"""

from common.permissions import IsAdmin, IsCustomer, IsSystemAdmin, IsVendor

__all__ = [
    "IsAdmin",
    "IsCustomer",
    "IsSystemAdmin",
    "IsVendor",
]