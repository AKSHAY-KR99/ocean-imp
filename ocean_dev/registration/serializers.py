import imp
from json import JSONDecoder, JSONEncoder
import json
import random
from urllib.request import Request
from django.contrib.auth import authenticate
from django.db.models import Q
from django.http import JsonResponse, request
from django.views.generic.base import ContextMixin
from inflection import re
from rest_framework import serializers
from django.conf import settings
from rest_framework.validators import UniqueValidator
from .models import User, LoginTrackerModel, UserDetailModel, UserDetailFilesModel, OnBoardEmailData, \
    UserContactDetails, OTP_SENT_STRING, ON_BOARD_STATUS_CHOICES, SMEOnBoardReviewEmailData
from utils.utility import get_user_available_amount, user_list_next_step, generate_request_next_step, \
    send_otp_for_login_or_set_password, get_user_available_amount, calculate_overdue_amount
from contact_app.models import LeadsModel
from contact_app.serializers import LeadsModelSerializers
from transaction_app.models import PaymentModel, CREDIT_PAYMENT_ACKNOWLEDGED, CREDIT_PAYMENT_PAID
from rest_framework.fields import EmailField, CharField


class RoleChoiceField(serializers.ChoiceField):
    """
    Class for generating the actual string value from the choice numbers eg:-(1, "ADMIN")
    """

    def to_representation(self, obj):
        if obj == '' and self.allow_blank:
            return obj
        return self._choices[obj]


class UserModelSerializers(serializers.ModelSerializer):
    """
    Serializers for User model
    """

    user_role = RoleChoiceField(choices=settings.ROLE_CHOICES)
    on_board_status = RoleChoiceField(choices=ON_BOARD_STATUS_CHOICES, read_only=True)
    email = EmailField(max_length=100, validators=[UniqueValidator(queryset=User.objects.all(),
                                                                   message="Email entered already exists")])
    phone_number = CharField(max_length=50, validators=[UniqueValidator(queryset=User.objects.all(),
                                                                        message='Phone number entered already exists')])

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'phone_number', 'user_role', 'credit_limit',
                  'currency_value', 'on_board_status', 'is_active', 'slug_value', 'is_staff', 'is_user_onboard',
                  'is_deleted', 'approved_by', 'on_boarding_details', 'master_contract', 'profile_image')
        extra_kwargs = {'email': {'required': True}, 'phone_number': {'required': True},
                        'is_staff': {"read_only": True}, 'slug_value': {"read_only": True},
                        'on_board_status': {"read_only": True},
                        'user_role': {'required': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)

        if LeadsModel.objects.filter(sign_up_email=validated_data['email']):
            raise serializers.ValidationError("Email entered already exists")
        elif LeadsModel.objects.filter(sign_up_phone_number=validated_data['phone_number']):
            raise serializers.ValidationError("Phone number entered already exists")
        return user

    # def validate_email(self, value):
    #     """
    #     Check if email entered already exist in Leads model
    #     """
    #     if LeadsModel.objects.filter(sign_up_email=value):
    #         raise serializers.ValidationError("Email entered already exists")
    #     return value
    #
    # def validate_phone_number(self, value):
    #     """
    #     Check if phone number entered already exist in Leads model
    #     """
    #     if LeadsModel.objects.filter(sign_up_phone_number=value):
    #         raise serializers.ValidationError("Phone number entered already exists")
    #     return value
    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        lead_object = LeadsModel.objects.filter(sign_up_email=response_data['email'])
        if lead_object.exists():
            response_data['requested_amount'] = lead_object[0].invoice_amount
        if response_data['on_boarding_details']:
            response_data['company_name'] = instance.on_boarding_details.company_name
            response_data['contact_person'] = instance.on_boarding_details.contact_person
            response_data['website'] = instance.on_boarding_details.company_website
            response_data['company_registered_address'] = instance.on_boarding_details.company_registered_address
        else:
            if lead_object.exists():
                response_data['company_name'] = lead_object[0].company_name
        leads_data = LeadsModelSerializers(instance=lead_object.last()).data
        response_data['country_name'] = leads_data["company_registered_in"]
        response_data["available_amount"] = get_user_available_amount(instance.id)
        response_data["used_amount"] = instance.credit_limit - get_user_available_amount(instance.id)
        over_due_amount = calculate_overdue_amount(instance)
        response_data["over_due_amount"] = over_due_amount
        if response_data["over_due_amount"] is None:
            response_data["over_due_amount"] = 0
        response_data["insured_by"] = None
        # response_data['invoice'] = False
        # if instance.user_role == settings.SME['number_value']:
        #     if FundInvoiceModel.objects.filter(sme=instance.id,
        #                                        application_status=FUND_INVOICE_APPROVED).exists():
        #         response_data['invoice'] = True
        # elif instance.user_role == settings.SUPPLIER['number_value']:
        #     if FundInvoiceModel.objects.filter(supplier=instance.id,
        #                                        application_status=FUND_INVOICE_APPROVED).exists():
        #         response_data['invoice'] = True
        response_data['payment_done'] = False
        if instance.user_role == settings.SME['number_value']:
            if PaymentModel.objects.filter(Q(acknowledgement_status=CREDIT_PAYMENT_ACKNOWLEDGED) |
                                           Q(acknowledgement_status=CREDIT_PAYMENT_PAID),
                                           payment_made_by=instance.id).exists():
                response_data['payment_done'] = True
        elif instance.user_role == settings.SUPPLIER['number_value']:
            if PaymentModel.objects.filter(Q(acknowledgement_status=CREDIT_PAYMENT_ACKNOWLEDGED) |
                                           Q(acknowledgement_status=CREDIT_PAYMENT_PAID),
                                           payment_made_by=instance.id).exists():
                response_data['payment_done'] = True
        next_step = user_list_next_step(instance, self.context['request'].user)
        response_data['next_step'] = next_step
        if 'over_due_from' in self.context and 'over_due_to' in self.context:
            if self.context['over_due_from'] == 0:
                if response_data["over_due_amount"] < self.context['over_due_to']:
                    return response_data
            if self.context['over_due_to'] == 0:
                if response_data["over_due_amount"] > self.context['over_due_from']:
                    return response_data
            if self.context['over_due_from'] <= response_data["over_due_amount"] <= self.context['over_due_to']:
                return response_data
        else:
            return response_data


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer class for validating the user from the user email and password. Also will send the otp
    """
    email = serializers.EmailField(max_length=255, write_only=True)
    password = serializers.CharField(max_length=128, write_only=True)
    session_id = serializers.UUIDField(read_only=True)

    def validate(self, data):
        user = authenticate(email=data.get("email", None), password=data.get("password", None))
        if user is None:
            raise serializers.ValidationError(
                'User login failed'
            )
        # function for generating otp
        otp_value = int(random.randint(100000, 999999))
        login_tracker_object = LoginTrackerModel.objects.create(user=user, otp_value=otp_value,
                                                                otp_status=OTP_SENT_STRING)
        login_tracker_object.save()

        # function for sending otp
        send_otp_for_login_or_set_password(user, otp_value)
        return {'session_id': str(login_tracker_object.session_id)}


class UserDetailFilesModelSerializers(serializers.ModelSerializer):
    """
    Serializer class for UserDetailFilesModel
    """

    class Meta:
        model = UserDetailFilesModel
        fields = ['detail', 'detail_file_key', 'detail_file_key', 'detail_id_file']
        extra_kwargs = {'detail': {"write_only": True}, 'detail_file_path': {"write_only": True}}


class UserContactDetailsSerializers(serializers.ModelSerializer):
    """
    Serializer class for UserContactDetails
    """

    class Meta:
        model = UserContactDetails
        fields = ['id', 'contact_person', 'contact_person_designation', 'contact_mobile_phone', 'contact_email']

    def create(self, validated_data):
        additional_user = UserContactDetails.objects.create(
            **validated_data, user_details=self.context['user_details'])
        return additional_user


class UserDetailSerializers(serializers.ModelSerializer):
    """
    Serializers for UserDetailModel Table
    """
    detail_id_files = UserDetailFilesModelSerializers(many=True, read_only=True)
    detail_id_contact = UserContactDetailsSerializers(many=True, read_only=True)

    class Meta:
        model = UserDetailModel
        fields = ['id', 'user_detail_path', 'company_name', 'company_registered_address', 'detail_id_contact',
                  'company_physical_address', 'company_registration_id', 'company_website', 'company_telephone_number',
                  'contact_person', 'contact_person_designation', 'contact_mobile_phone', 'contact_email',
                  'no_full_time_employees', 'last_fy_annual_revenue', 'total_debt_amounts', 'inventory_on_hand',
                  "current_balance_sheet", "last_year_account_statement", "last_year_profit_loss",
                  'last_years_annual_reports', 'ytd_management_accounts', 'last_bank_statements',
                  'directors_address_proof', 'share_holding_corporate_structure', 'cap_table', 'trade_cycle_po',
                  'trade_cycle_invoice', 'trade_cycle_bl', 'trade_cycle_awb', 'trade_cycle_packing_list',
                  'trade_cycle_sgs_report', 'detail_id_files', 'date_created', 'date_modified',
                  'additional_info', 'company_details']
        extra_kwargs = {'user_detail_path': {"write_only": True}, 'detail_id_files': {"read_only": True},
                        'company_details': {"read_only": True}}


class SupplierSmeDetailSerializers(serializers.ModelSerializer):
    """
    Serializers for getting the supplier/sme details
    """
    company_name = serializers.CharField(source='on_boarding_details.company_name', read_only=True)
    company_website = serializers.CharField(source='on_boarding_details.company_website', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'company_name', 'last_name', 'email', 'company_website', 'phone_number']


class OnBoardEmailDataSerializers(serializers.ModelSerializer):
    """
    Serializers for getting the OnBoardEmailData
    """

    class Meta:
        model = OnBoardEmailData
        fields = '__all__'
        extra_kwargs = {'id': {"read_only": True}, 'date_created': {"read_only": True}}


class SMEOnboardReviewMailDataSerializer(serializers.ModelSerializer):
    """
    Serializer  for getting the SME on-board review sending mails
    """

    class Meta:
        model = SMEOnBoardReviewEmailData
        fields = ['id', 'user_detail', 'email', 'date_created']
        extra_kwargs = {'id': {"read_only": True}, 'date_created': {"read_only": True},
                        'user_detail': {"required": False}}

    def create(self, validated_data):
        review_mail_model = SMEOnBoardReviewEmailData.objects.create(
            **validated_data, user_detail=self.context['user_detail']
        )
        return review_mail_model
