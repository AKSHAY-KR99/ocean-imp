from django.contrib import admin
from . import models
from django.contrib import admin
from utils.utility import contact_info_send_email


class ContactAdmin(admin.ModelAdmin):

    def save_model(self, request, obj, form, change):
        output_data = {'name': form.cleaned_data.get('name'), 'mobile': form.cleaned_data.get('mobile'),
                       'email_address': form.cleaned_data.get('email_address'),
                       'message': form.cleaned_data.get('message')}

        # Sending email to the admin email(on adding a new data in ContactModel)
        contact_info_send_email(request, output_data)
        super().save_model(request, obj, form, change)


# Register your models here.
admin.site.register(models.ContactModel, ContactAdmin)
admin.site.register(models.LeadsModel)
admin.site.register(models.LeadStatusModel)
