from rest_framework import serializers, status
from django.conf import settings
from django_countries.serializer_fields import CountryField
from django_countries.serializers import CountryFieldMixin
from rest_framework.response import Response
from rest_framework.validators import UniqueValidator
from rest_framework.fields import EmailField, CharField
from django.contrib.auth import get_user_model
from .models import LeadsModel, ContactModel, LeadStatusModel, LEAD_ON_BOARD_STATUS_CHOICES, \
    ON_BOARDING_LEAD, ON_BOARDING_CUSTOMER
from transaction_app.models import FundInvoiceModel
from django.db.models import Q
from utils.utility import leads_next_step

User = get_user_model()


class RoleChoiceField(serializers.ChoiceField):
    """
    Class for generating the actual string value from the choice numbers eg:-(1, "Admin")
    """

    def to_representation(self, obj):
        if obj == '' and self.allow_blank:
            return obj
        return self._choices[obj]


class LeadsModelSerializers(CountryFieldMixin, serializers.ModelSerializer):
    """
    Serializer class for LeadsModel model
    """
    company_registered_in = CountryField(name_only=True)
    role = RoleChoiceField(choices=settings.ROLE_CHOICES)
    current_status = RoleChoiceField(choices=LEAD_ON_BOARD_STATUS_CHOICES)
    sign_up_email = EmailField(max_length=100,
                               validators=[UniqueValidator(queryset=LeadsModel.objects.all(),
                                                           message="Email entered already exists")])
    sign_up_phone_number = CharField(max_length=50, validators=[UniqueValidator(queryset=LeadsModel.objects.all(),
                                                                                message="Phone number entered already exists")])

    class Meta:
        model = LeadsModel
        fields = ['id', 'first_name', 'last_name', 'role', 'company_name', 'company_email', 'company_website',
                  'phone_number', 'company_registered_in', 'annual_revenue', 'description', 'current_status',
                  'created_by', 'alternate_phone_number', 'alternate_email', 'submitted_date',
                  'sign_up_email', 'sign_up_phone_number', 'invoice_amount', 'company_id', 'sync_status']

    def validate_sign_up_phone_number(self, value):
        """
        Check if signup phone number entered already exist in User model
        """

        if (self.instance and User.objects.filter(phone_number=value).exclude(
                phone_number=self.instance.sign_up_phone_number)) or \
                (not self.instance and User.objects.filter(phone_number=value)):
            raise serializers.ValidationError("Phone number entered already exists")
        return value

    def validate_sign_up_email(self, value):
        """
        Check if email entered already exists in User model
        """

        if (self.instance and User.objects.filter(email=value).exclude(email=self.instance.sign_up_email)) or \
                (not self.instance and User.objects.filter(email=value)):
            raise serializers.ValidationError("Email entered already exists")
        return value

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        if instance is not None:
            sme_obj = User.objects.filter(email=instance.sign_up_email)
            if sme_obj.exists():
                response_data['sme_id'] = sme_obj.first().id
                response_data['sme_master_contract'] = None
                if sme_obj.first().master_contract is not None:
                    response_data['sme_master_contract'] = sme_obj.first().master_contract.id
                if sme_obj.first().on_boarding_details is not None:
                    response_data['on_boarding_details'] = sme_obj.first().on_boarding_details.id
                next_step = leads_next_step(sme_obj.first())
            else:
                if instance.current_status == ON_BOARDING_LEAD:
                    next_step = settings.ADMIN_APPROVE_OR_REJECT
                else:
                    next_step = settings.NO_ACTION_NEEDED

            response_data['next_step'] = next_step
            return response_data


class ContactModelSerializers(serializers.ModelSerializer):
    """
    Serializer for ContactModel model
    """

    class Meta:
        model = ContactModel
        fields = '__all__'


class LeadStatusModelSerializers(serializers.ModelSerializer):
    """
    Serializer for LeadStatusModel
    """

    class Meta:
        model = LeadStatusModel
        fields = '__all__'
