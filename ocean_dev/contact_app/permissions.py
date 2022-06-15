from rest_framework.permissions import BasePermission
from django.conf import settings


class IsAdminOrCreateOnly(BasePermission):
    """
    Class for setting permission for giving Anonymous User permission only to create new data and giving permission for
    Admin User to read data
    """

    SAFE_METHODS = ['POST']

    def has_permission(self, request, view):
        if request.method in self.SAFE_METHODS:
            return True
        else:
            if request.user.is_authenticated:
                return request.user.is_superuser or request.user.is_staff or request.user.user_role == settings.ADMIN["number_value"]
            else:
                return False

