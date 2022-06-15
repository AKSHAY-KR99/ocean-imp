from django.contrib import admin
from . import models


# Register your models here.
class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'email', 'first_name', 'last_name', 'on_board_status', 'user_role', 'is_active', 'is_deleted']
    list_filter = ['user_role', 'is_active', 'is_deleted', 'on_board_status', 'date_created']
    search_fields = ['email', 'first_name', 'last_name']


admin.site.register(models.User, UserAdmin)
admin.site.register(models.LoginTrackerModel)
admin.site.register(models.UserDetailModel)
admin.site.register(models.XeroAuthTokenModel)
admin.site.register(models.OnBoardEmailData)
admin.site.register(models.UserContactDetails)
admin.site.register(models.SMEOnBoardReviewEmailData)
