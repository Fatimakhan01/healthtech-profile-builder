from rest_framework.permissions import BasePermission

from .models import User


class IsStandardUser(BasePermission):
    message = "A standard-user account is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role == User.Role.STANDARD
        )
