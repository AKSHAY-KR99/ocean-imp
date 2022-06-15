from django.db import models
from django.db.models.signals import post_save
from django.conf import settings
from django_countries.fields import CountryField
from utils.model_utility import lead_send_email, send_lead_rejected_email

# lead status choices data
ON_BOARDING_LEAD = 1
ON_BOARDING_REJECTED = 2
ON_BOARDING_CUSTOMER = 3

LEAD_ON_BOARD_STATUS_CHOICES = ((ON_BOARDING_LEAD, "Lead"), (ON_BOARDING_REJECTED, "Rejected"),
                                (ON_BOARDING_CUSTOMER, "Customer"))


class LeadsModel(models.Model):
    """
    Model class for Leads Table (sme/supplier contact info)
    """

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    company_email = models.EmailField(max_length=200, blank=False)
    company_website = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=50, blank=True)
    company_registered_in = CountryField()
    annual_revenue = models.CharField(max_length=100, blank=True, default=None)
    invoice_amount = models.DecimalField(max_digits=20, decimal_places=3, null=True, default=0, blank=True)
    description = models.TextField(blank=True)
    role = models.PositiveSmallIntegerField(choices=settings.ROLE_CHOICES, blank=True, null=True)
    alternate_email = models.EmailField(max_length=200, blank=True)
    sign_up_email = models.EmailField(max_length=200, blank=True, unique=True)
    alternate_phone_number = models.CharField(max_length=50, blank=True)
    sign_up_phone_number = models.CharField(max_length=50, blank=True, unique=True)
    current_status = models.PositiveSmallIntegerField(choices=LEAD_ON_BOARD_STATUS_CHOICES, blank=True, null=True)
    submitted_date = models.DateField(auto_now_add=True)
    created_by = models.ForeignKey('registration.User', on_delete=models.SET_NULL, blank=True, null=True,
                                   related_name="leads_created_by")
    is_deleted = models.BooleanField(default=False)
    company_id = models.CharField(max_length=200, blank=True, null=True)
    sync_status = models.CharField(max_length=100, default=settings.NO_SYNC)
    is_mail_send = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        # Checking if model instance is created (new entry)
        if not self.current_status:
            self.current_status = ON_BOARDING_LEAD
        super().save(*args, **kwargs)

    def __str__(self):
        return self.company_email


class LeadStatusModel(models.Model):
    """
    Model for storing the status related data of a LeadsModel
    """
    lead = models.ForeignKey(LeadsModel, on_delete=models.CASCADE, related_name="lead_status")
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="lead_status_action_by")
    status_created_date = models.DateField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    status = models.PositiveSmallIntegerField(choices=LEAD_ON_BOARD_STATUS_CHOICES, blank=True, null=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return str(self.status)


class ContactModel(models.Model):
    """
    Model class for Contact Table (Contact form)
    """
    name = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    email_address = models.EmailField(max_length=200, blank=False)
    message = models.TextField(blank=True)

    def __str__(self):
        return self.email_address


def send_email_lead_save_signal(instance, **kwargs):
    """
    Initiating sending mails when LeadsModel is created
    """
    if instance.current_status == ON_BOARDING_LEAD and not instance.is_mail_send:

        lead_send_email(subject=settings.SENDING_LEADS_DATA, model_instance=instance,
                        recipient_email=settings.ADMIN_EMAIL)
        instance.is_mail_send = True
        instance.save()

    elif instance.current_status == ON_BOARDING_REJECTED:
        send_lead_rejected_email(subject=settings.REJECTED_LEADS_DATA, model_instance=instance,
                                 recipient_email=instance.sign_up_email)


# def send_email_contact_save_signal(instance, **kwargs):
#     """
#     Initiating sending mails when ContactModel is created
#     """
#     contact_send_email(subject=settings.SENDING_CONTACTS_DATA, model_instance=instance,
#                        recipient_email=settings.ADMIN_EMAIL)


post_save.connect(send_email_lead_save_signal, sender=LeadsModel)

# post_save.connect(send_email_contact_save_signal, sender=ContactModel)
