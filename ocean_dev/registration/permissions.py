from rest_framework.permissions import BasePermission
from django.conf import settings


class IsCustomAdminUser(BasePermission):
    """
    Class for giving permission only for Admin Users(is_staff=True)
    """

    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return request.user.is_superuser or request.user.is_staff or request.user.user_role == settings.ADMIN["number_value"]
        else:
            return False


class IsUserCreateOnlyOrAdmin(BasePermission):
    """
    Class for setting permission for giving authenticated User permission only to create new data and
    giving permission for Admin User to read data
    """

    SAFE_METHODS = ['POST', 'PUT']

    def has_permission(self, request, view):
        if request.method in self.SAFE_METHODS:
            return request.user.is_authenticated
        else:
            if request.user.is_authenticated:
                return request.user.is_superuser or request.user.is_staff or request.user.user_role == settings.ADMIN["number_value"]
            else:
                return False
