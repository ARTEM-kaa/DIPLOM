from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission, SAFE_METHODS


User = get_user_model()


class IsAdmin(BasePermission):
    """Allow access only to admin users (role=admin)."""

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == User.Role.ADMIN
        )


class IsCommander(BasePermission):
    """Allow access only to commander users."""

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == User.Role.COMMANDER
        )


class IsCommanderOrAdmin(BasePermission):
    """Commander or admin (e.g. approve duty replacements)."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(request.user, "role", None) in (
            User.Role.COMMANDER,
            User.Role.ADMIN,
        )


class IsSoldier(BasePermission):
    """Allow access only to soldier users."""

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == User.Role.SOLDIER
        )


class IsOwnerOrCommander(BasePermission):
    """
    Object-level permission: owner of object or commander/admin.
    For User objects owner is the user itself.
    For other objects tries attributes 'requester', 'requested_replacement',
    or 'user' as owner.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, "role", None) in (
            User.Role.COMMANDER,
            User.Role.ADMIN,
        ):
            return True

        if isinstance(obj, User):
            return obj == request.user

        owners = [
            getattr(obj, "requester", None),
            getattr(obj, "requested_replacement", None),
            getattr(obj, "user", None),
        ]
        return request.user in owners


class CanManageDuties(BasePermission):
    """Allow commanders and admins to manage duties."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return getattr(request.user, "role", None) in (
            User.Role.COMMANDER,
            User.Role.ADMIN,
        )

