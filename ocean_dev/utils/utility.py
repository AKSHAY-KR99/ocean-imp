import base64
from calendar import month
import imp
import boto3
import math
import os
import pdfkit
import jwt
import requests
from docusign_esign.client.api_exception import ArgumentException
from jinja2 import Template
import json
import pandas as pd
import threading
import xlsxwriter
# from google_currency import convert
import shutil
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from smtplib import SMTPException
from django.db.models import Sum, Q
from django.contrib.auth import get_user_model
from django_user_agents.utils import get_user_agent
from django.utils.translation import get_language_from_request
from docusign_esign import ApiClient, EnvelopesApi, Document, Signer, SignHere, Tabs, \
    EnvelopeDefinition, Recipients, RecipientViewRequest, DateSigned, Text
from cryptography.hazmat.primitives import serialization as crypto_serialization
from time import time
from datetime import date, datetime, timedelta
# from ocean_backend.ocean_dev.ocean_dev.settings import SYNC_COMPLETED
from transaction_app import models
# from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from registration.models import ON_BOARD_PASSWORD_SET, ON_BOARD_USER_CREATED, ON_BOARD_IN_PROGRESS, \
    ON_BOARD_USER_REVIEWED, ON_BOARD_COMPLETED, XeroAuthTokenModel, UserDetailModel
import logging

User = get_user_model()


def send_email_utility(subject, message, recipient_email, from_email=settings.EMAIL_DEFAULT_EMAIL):
    """
    Function for sending emails

    :param from_email: email id of sender
    :param subject: subject of the email
    :param message: message body
    :param recipient_email: email id of recipient
    """
    try:
        send_mail(subject=subject, message=message, recipient_list=[recipient_email], fail_silently=False,
                  from_email=from_email, html_message=message)
    except SMTPException as error:
        logging.error(f"Utility - send_email_utility error = {str(error)}")


def contact_info_send_email(request, contact_data):
    """
    Function for sending email to the admin email(on adding a new data in ContactModel)

    :param request: request
    :param contact_data: model instance
   :return:
    """
    # Getting the device by which the user has entered the data
    user_agent = get_user_agent(request)
    if user_agent.is_mobile:
        device = 'Mobile'
    elif user_agent.is_tablet:
        device = 'Mobile'
    else:
        device = 'Desktop'

    contact_data['device'] = device
    contact_data['language'] = get_language_from_request(request)
    message = render_to_string('contacts_app/contact_info.html', {'contact_data': contact_data,
                                                                  'logo_path': settings.BACKEND_URL[
                                                                               :-1] + settings.MEDIA_URL + 'logo/'})
    send_email_utility(settings.SENDING_CONTACTS_DATA, message, settings.ADMIN_EMAIL)


def user_activated_send_email(subject, model_instance, recipient_email):
    """
    Function for sending email to the newly activated (by admin) user

    :param subject: subject of the email
    :param model_instance: model instance
    :param recipient_email: email id of recipient
    :return:
    """

    message = render_to_string('registration/user_activated.html', {
        'instance_data': model_instance,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/',
        'login_link': f'{settings.FRONTEND_URL}{settings.FRONTEND_LOGIN_URL}'
    })
    send_email_utility(subject, message, recipient_email)


def user_deactivated_send_email(subject, model_instance, recipient_email):
    """
    Function for sending email when user is been deactivated (by admin)

    :param subject: subject of the email
    :param model_instance: model instance
    :param recipient_email: email id of recipient
    :return:
    """

    message = render_to_string('registration/user_deactivated.html', {
        'instance_data': model_instance,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/',
        'login_link': f'{settings.FRONTEND_URL}{settings.FRONTEND_LOGIN_URL}'
    })
    send_email_utility(subject, message, recipient_email)


def generate_next_step_value(current_step, user_object):
    """
    Function for generating next_step constants (On boarding flow) based on the current_step and user data

    :param current_step: String constants showing the login stage
    :param user_object: user model instance
    :return:
    """
    from registration import models
    if current_step == settings.APP_USER_DETAIL_PAGE:
        if user_object.is_user_onboard:
            next_step = settings.NO_ACTION_NEEDED
        elif user_object.on_board_status in [models.ON_BOARD_USER_CREATED, models.ON_BOARD_PASSWORD_SET,
                                             models.ON_BOARD_REJECTED]:
            next_step = settings.USER_ACTION_NEEDED
        elif user_object.on_board_status in [models.ON_BOARD_IN_PROGRESS, models.ON_BOARD_USER_REVIEWED]:
            next_step = settings.ADMIN_ACTION_NEEDED
        return next_step

    elif current_step == settings.APP_USER_LIST_PAGE:
        if user_object.is_user_onboard:
            next_step = settings.NO_ACTION_NEEDED
        elif user_object.on_board_status in [models.ON_BOARD_USER_CREATED, models.ON_BOARD_PASSWORD_SET,
                                             models.ON_BOARD_REJECTED]:
            next_step = settings.USER_ACTION_NEEDED
        elif user_object.on_board_status in [models.ON_BOARD_IN_PROGRESS, models.ON_BOARD_USER_REVIEWED]:
            next_step = settings.ADMIN_ACTION_NEEDED
        return next_step

    elif current_step == settings.APP_AUTH_TOKEN_GENERATOR:
        if user_object.is_user_onboard:
            next_step = settings.DIRECT_TO_DASHBOARD
        elif user_object.on_board_status == models.ON_BOARD_PASSWORD_SET:
            next_step = settings.CREATE_DETAILS_PAGE
        elif user_object.on_board_status in [models.ON_BOARD_IN_PROGRESS, models.ON_BOARD_USER_REVIEWED]:
            next_step = settings.DETAIL_PAGE_ADMIN_APPROVAL_NEEDED
        elif user_object.on_board_status == models.ON_BOARD_REJECTED:
            next_step = settings.EDIT_DETAILS_PAGE
        return next_step

    elif current_step == settings.APP_FROM_EMAIL_SLUG_VALUE:
        if user_object.on_board_status == models.ON_BOARD_USER_CREATED or user_object.is_reset_password:
            next_step = settings.APP_PASSWORD_SET_PAGE
        else:
            next_step = settings.APP_LOGIN_PAGE
        return next_step


def get_user_available_amount(user_id):
    """
    Function for getting the available amount against a user

    :param user_id: id of the user
    :return: available_amount
    """
    # Imported inside function to prevent circular import error
    from transaction_app.models import FundInvoiceModel, FUND_INVOICE_INITIATED, FUND_INVOICE_APPROVED
    sum_object = FundInvoiceModel.objects.filter(Q(application_status=FUND_INVOICE_INITIATED) | Q(
        application_status=FUND_INVOICE_APPROVED), sme=user_id, is_deleted=False). \
        aggregate(Sum("invoice_total_amount"))
    if sum_object['invoice_total_amount__sum']:
        used_amount = sum_object["invoice_total_amount__sum"]
    else:
        used_amount = 0
    user_object = User.objects.get(id=user_id)
    available_amount = user_object.credit_limit - used_amount
    return round(available_amount, 3)


def generate_request_status(user_action, is_master_contract=False):
    """
    Function for generating request status and assign to (user) based on the current action and user

    :param user_action: user action
    :return: [action_taken, next_assign_to]
    """

    if user_action == settings.CREDIT_REQUEST_CREATED:
        return [settings.CREDIT_REQUEST_CREATED, settings.ADMIN["name_value"]]
    elif user_action == settings.CREDIT_REQUEST_ADMIN_APPROVED:
        return [settings.CREDIT_REQUEST_ADMIN_APPROVED, settings.ADMIN["name_value"]]
    elif user_action == settings.CREDIT_REQUEST_ADMIN_REJECTED:
        return [settings.CREDIT_REQUEST_ADMIN_REJECTED, settings.SME["name_value"]]
    elif user_action == settings.CREDIT_CONTRACT_ADMIN_CREATED:
        return [settings.CREDIT_CONTRACT_ADMIN_CREATED, settings.ADMIN["name_value"]]
    elif user_action == settings.CREDIT_CONTRACT_ADMIN_SIGNED:
        return [settings.CREDIT_CONTRACT_ADMIN_SIGNED, settings.SME["name_value"]]
    # elif user_action == settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE:
    #     return [settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE, settings.SME["name_value"]]
    elif user_action == settings.CREDIT_CONTRACT_SME_APPROVED:
        if is_master_contract:
            return [settings.CREDIT_CONTRACT_SME_APPROVED, settings.SME["name_value"]]
        return [settings.CREDIT_CONTRACT_SME_APPROVED, settings.SUPPLIER["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_SUPPLIER_CREATED:
        return [settings.CREDIT_SHIPMENT_SUPPLIER_CREATED, settings.SME["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_SME_CREATED:
        return [settings.CREDIT_SHIPMENT_SME_CREATED, settings.SUPPLIER["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED:
        return [settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED, settings.ADMIN["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_SME_SEND_BACK:
        return [settings.CREDIT_SHIPMENT_SME_SEND_BACK, settings.SUPPLIER["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_SUPPLIER_SEND_BACK:
        return [settings.CREDIT_SHIPMENT_SUPPLIER_SEND_BACK, settings.SME["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED:
        return [settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED, settings.ADMIN["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SUPPLIER_UPLOADED:
        return [settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SUPPLIER_UPLOADED, settings.SME["name_value"]]
    elif user_action == settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SME_UPLOADED:
        return [settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SME_UPLOADED, settings.SUPPLIER["name_value"]]

        # elif user_action == settings.CREDIT_SHIPMENT_ADMIN_APPROVED:
    #     return [settings.CREDIT_SHIPMENT_ADMIN_APPROVED, settings.SME["name_value"]]
    # elif user_action == settings.CREDIT_SHIPMENT_ADMIN_REJECTED:
    #     return [settings.CREDIT_SHIPMENT_ADMIN_REJECTED, settings.SUPPLIER["name_value"]]


def generate_request_next_step(action_taken, current_user_role, is_master_contract=False):
    """
    Function for generating the next action in the fund invoice phase

    :param action_taken: last action taken
    :param current_user_role: viewing user role
    :return: next_step
    """
    if action_taken == settings.CREDIT_REQUEST_CREATED:
        if current_user_role == settings.ADMIN["name_value"]:
            return settings.CREDIT_ADMIN_APPROVAL_NEEDED
        else:
            return settings.REQUEST_NO_ACTION_NEEDED

    # elif action_taken == settings.CREDIT_REQUEST_ADMIN_APPROVED:
    #
    #     if current_user_role == settings.ADMIN["name_value"]:
    #         return settings.CREDIT_ADMIN_CREATE_CONTRACT
    #     else:
    #         return settings.REQUEST_NO_ACTION_NEEDED
    elif action_taken == settings.CREDIT_REQUEST_ADMIN_REJECTED:
        if current_user_role == settings.SME["name_value"]:
            return settings.CREDIT_CREATE_INVOICE_REQUEST
        else:
            return settings.REQUEST_NO_ACTION_NEEDED

    elif action_taken == settings.CREDIT_CONTRACT_ADMIN_CREATED:
        if current_user_role == settings.ADMIN["name_value"]:
            return settings.CREDIT_CONTRACT_ADMIN_TO_SIGN
        else:
            return settings.REQUEST_NO_ACTION_NEEDED

    elif action_taken == settings.CREDIT_CONTRACT_ADMIN_SIGNED:
        if current_user_role == settings.SME["name_value"]:
            return settings.CREDIT_CONTRACT_SME_APPROVAL_NEEDED
        else:
            return settings.REQUEST_NO_ACTION_NEEDED

    # elif action_taken == settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE:
    #     if current_user_role == settings.SME["name_value"]:
    #         return settings.CREDIT_CONTRACT_SME_APPROVAL_NEEDED
    #     else:
    #         return settings.REQUEST_NO_ACTION_NEEDED

    elif action_taken == settings.CREDIT_CONTRACT_SME_APPROVED:
        if is_master_contract:
            if current_user_role == settings.SME["name_value"]:
                return settings.CREDIT_CREATE_INVOICE_REQUEST
            else:
                return settings.REQUEST_NO_ACTION_NEEDED
        else:
            if current_user_role in [settings.SUPPLIER["name_value"], settings.SME["name_value"]]:
                return settings.CREDIT_CREATE_SHIPMENT
            else:
                return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_SUPPLIER_CREATED:
        if current_user_role == settings.SME["name_value"]:
            return settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGMENT_NEEDED
        else:
            return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_SME_CREATED:
        if current_user_role == settings.SUPPLIER["name_value"]:
            return settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGMENT_NEEDED
        else:
            return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED:
        return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED:
        return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_SME_SEND_BACK:
        if current_user_role == settings.SUPPLIER["name_value"]:
            return settings.CREDIT_SHIPMENT_ADDITIONAL_FILES_SUPPLIER_UPLOAD_NEEDED
        else:
            return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_SUPPLIER_SEND_BACK:
        if current_user_role == settings.SME["name_value"]:
            return settings.CREDIT_SHIPMENT_ADDITIONAL_FILES_SME_UPLOAD_NEEDED
        else:
            return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SUPPLIER_UPLOADED:
        if current_user_role == settings.SME["name_value"]:
            return settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGMENT_NEEDED
        else:
            return settings.CREDIT_PAYMENT_VIEW

    elif action_taken == settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SME_UPLOADED:
        if current_user_role == settings.SUPPLIER["name_value"]:
            return settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGMENT_NEEDED
        else:
            return settings.CREDIT_PAYMENT_VIEW
    else:
        return settings.REQUEST_NO_ACTION_NEEDED

    # elif action_taken == settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED:
    #     if current_user_role == settings.ADMIN["name_value"]:
    #         return settings.CREDIT_SHIPMENT_ADMIN_APPROVAL_NEEDED
    #     else:
    #         return settings.CREDIT_PAYMENT_VIEW

    # elif action_taken == settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED:
    #     if current_user_role == settings.ADMIN["name_value"]:
    #         return settings.CREDIT_SHIPMENT_ADMIN_APPROVAL_NEEDED
    #     else:
    #         return settings.CREDIT_PAYMENT_VIEW

    # elif action_taken == settings.CREDIT_SHIPMENT_ADMIN_REJECTED:
    #     if current_user_role == settings.SUPPLIER["name_value"]:
    #         return settings.REQUEST_NO_ACTION_NEEDED
    #     else:
    #         return settings.REQUEST_NO_ACTION_NEEDED

    # elif action_taken == settings.CREDIT_SHIPMENT_ADMIN_APPROVED:
    #     return settings.CREDIT_PAYMENT_VIEW


# def convert_currency_value(currency_from, currency_to, currency_amount):
#     """
#     Function for converting money value using currency_from and currency_to values
#
#     :param currency_from: currency the amount is now
#     :param currency_to: currency to which the amount needs to be converted
#     :param currency_amount: money value
#     :return: converted money value
#     """
#     converted_value = json.loads(convert(currency_from.lower(), currency_to.lower(), float(currency_amount)))
#     return converted_value["amount"]


def create_user(lead_object, alternate_phone_number=None):
    """
    Function for creating a user
    :param alternate_phone_number: alternate phone number passed by admin
    :param lead_object: lead object instance
    :return:
    """
    if alternate_phone_number:
        phone_number = alternate_phone_number
    else:
        phone_number = lead_object.phone_number
    User.objects.create_user(email=lead_object.sign_up_email, first_name=lead_object.first_name,
                             last_name=lead_object.last_name,
                             phone_number=phone_number, user_role=lead_object.role, credit_limit=0,
                             currency_value="USD")


def check_sme_missing_field_onboarding(data_keys, is_xero_files_added):
    """
    Function for checking if all the fields are present in the request

    :param data_keys: list of request data keys
    :return: True/False
    """
    key_status = True
    if is_xero_files_added:
        for key in settings.ON_BOARDING_SME_NEEDED_KEY_WITH_XERO:
            if key not in data_keys:
                key_status = False
    else:
        for key in settings.ON_BOARDING_SME_NEEDED_KEY_WITHOUT_XERO:
            if key not in data_keys:
                key_status = False
    # id key not mandatory
    # id_key_status = False
    # if set(settings.USER_DETAIL_ID_KEY) & set(data_keys):
    #     id_key_status = True
    return key_status


def check_sme_terms_valid(terms_data, is_installment):
    """
    Function for checking if sme terms added is valid

    :param is_installment: True/False
    :param terms_data: list of terms added
    :return: response_data: [terms_valid_status, balance_type_value, error_message, amount_type]
    """
    from transaction_app import models
    if not terms_data:
        return [False, None, "Please add the terms data"]
    if is_installment:
        if terms_data['units'] < 1:
            return [False, None, "Cannot add units less than 1"]
        if terms_data['period'] not in [models.INSTALLMENT_PERIOD_WEEKLY, models.INSTALLMENT_PERIOD_MONTHLY]:
            return [False, None, "Please select a valid period type"]
        return [True, None, None]
    else:
        total_value = 0
        percent_type = False
        amount_type = False
        balance_type = False
        # Check for valid criteria
        criteria_status = check_for_valid_payment_criteria(terms_data)
        if not criteria_status[0]:
            return [False, None, criteria_status[1]]

        for terms_check in terms_data:
            if terms_check['type'] == models.TERMS_TYPE_BALANCE:
                balance_type = True
            elif terms_check['type'] == models.TERMS_TYPE_AMOUNT:
                amount_type = True
            elif terms_check['type'] == models.TERMS_TYPE_PERCENTAGE:
                percent_type = True
            if 'value' in list(terms_check.keys()):
                if terms_check['value'] <= 0:
                    return [False, None, "Cannot add negative or zero values in payment terms"]
                total_value += terms_check['value']
        if amount_type and percent_type:
            return [False, None, "Cannot add both amount and percentage in payment terms"]
        if percent_type:
            if balance_type:
                if total_value < 100:
                    return [True, 100 - total_value, None, models.TERMS_TYPE_PERCENTAGE]
                else:
                    return [False, None, "Total value should be less than 100 as balance is added in payment terms"]
            else:
                if total_value == 100:
                    return [True, None]
                else:
                    return [False, None, "Total of value should be equal to 100 in payment terms"]
        elif amount_type:
            if balance_type:
                return [True, 0, None, models.TERMS_TYPE_BALANCE]
            else:
                return [True, None]
        else:
            return [False, None, "Check the value added in payment terms"]


def check_supplier_terms_valid(terms_data):
    """
    Function for checking if supplier terms added is valid

    :param terms_data: list of terms added
    :return: response_data: [terms_valid_status, balance_type_value, error_message, amount_type]
    """
    from transaction_app import models
    total_value = 0
    balance_type = False
    after_shipment = False
    for terms_check in terms_data:
        if terms_check['value_type'] == models.TERMS_TYPE_BALANCE:
            balance_type = True
        elif terms_check['value_type'] == models.TERMS_TYPE_PERCENTAGE:
            pass
        else:
            return [False, None, "Please check the value type added"]
        # Check for before shipment term added after adding after shipment term
        if not terms_check["before_shipment"]:
            after_shipment = True
        else:
            if terms_check["before_shipment"] and after_shipment:
                return [False, None, "Cannot add term with before shipment after adding term with after shipment"]

        if 'value' in list(terms_check.keys()):
            if terms_check['value'] <= 0:
                return [False, None, "Cannot add negative or zero values in payment terms"]
            total_value += terms_check['value']

    if balance_type:
        if total_value < 100:
            return [True, 100 - total_value, None, models.TERMS_TYPE_PERCENTAGE]
        else:
            return [False, None, "Total value should be less than 100 as balance is added in payment terms"]
    else:
        if total_value == 100:
            return [True, None]
        else:
            return [False, None, "Total of value should be equal to 100 in payment terms"]


def check_contract_type_valid(contract_type_data, is_create=True):
    """
    Function for checking if contract type is valid

    :param contract_type_data: contract type request data
    :return: response_data: [terms_valid_status, error_message]
    """
    from transaction_app import models
    # Check for gross margin and markup values
    if "gross_margin" in contract_type_data and "markup" in contract_type_data:
        if not 0 < contract_type_data["gross_margin"] <= 100:
            return [False, "Gross margin value should be in range of 1 to 100"]
        if not 0 < contract_type_data["markup"] <= 100:
            return [False, "Markup value should be in range of 1 to 100"]
    else:
        return [False, "Please add both Gross margin and Markup values"]

    if contract_type_data.get('fixed_fee_value'):
        if contract_type_data.get('fixed_fee_type') == models.TERMS_TYPE_AMOUNT:
            if not float(contract_type_data["fixed_fee_value"]).is_integer():
                return [False, "Please enter a whole number value"]
        elif contract_type_data.get('fixed_fee_type') == models.TERMS_TYPE_PERCENTAGE:
            if not 0 < contract_type_data["fixed_fee_value"] <= 100:
                return [False, "Fixed fee value should be in range of 1 to 100"]
        else:
            return [False, "Please check the fixed fee type selected"]

    if is_create:
        if not models.PaymentTermModel.objects.filter(id=contract_type_data['payment_terms'], for_sme=True,
                                                      is_delete=False).exists():
            return [False, "Please check the payment term selected"]

    return [True, "Check complete no issues found"]


def calculate_total_sales_amount(fund_invoice_object, contract_object):
    """
    Function for calculating the total sales amount
    :param fund_invoice_object: fund invoice object instance
    :param contract_object: contract object instance
    :return: [total_sales_amount, fixed_fee_value]
    """
    from transaction_app import models

    invoice_amount = fund_invoice_object.invoice_total_amount
    total_sales_amount = float(invoice_amount) + (float(fund_invoice_object.markup if fund_invoice_object.markup \
                                                            else contract_object.markup) * float(invoice_amount)) / 100
    if contract_object.fixed_fee_type == models.TERMS_TYPE_AMOUNT:
        if fund_invoice_object.contract_category is not None and fund_invoice_object.fixed_fee_value != contract_object.fixed_fee_value:
            fixed_fee_value = round(float(fund_invoice_object.fixed_fee_value), 3)
            total_sales_amount += fixed_fee_value
        else:
            fixed_fee_value = round(float(contract_object.fixed_fee_value), 3)
            total_sales_amount += fixed_fee_value
    elif contract_object.fixed_fee_type == models.TERMS_TYPE_PERCENTAGE:
        if fund_invoice_object.contract_category is not None and fund_invoice_object.fixed_fee_value != contract_object.fixed_fee_value:
            fixed_fee_value = round(((float(fund_invoice_object.fixed_fee_value) * float(invoice_amount)) / 100), 3)
            total_sales_amount += fixed_fee_value
        else:
            fixed_fee_value = round(((float(contract_object.fixed_fee_value) * float(invoice_amount)) / 100), 3)
            total_sales_amount += fixed_fee_value
    else:
        fixed_fee_value = None
    return [round(total_sales_amount, 3), fixed_fee_value]


def list_contract_next_step(last_action_taken, current_user):
    """
    Function to list (contract listing) the next actions of a user
    :param last_action_taken: last action taken
    :param current_user: viewing user role
    :return: next action
    """
    if current_user == settings.ADMIN["name_value"]:
        if last_action_taken == settings.CREDIT_CONTRACT_ADMIN_CREATED:
            return settings.CREDIT_CONTRACT_ADMIN_TO_SIGN
        # elif last_action_taken == settings.CREDIT_CONTRACT_ADMIN_SIGNED:
        #     return settings.CREDIT_CONTRACT_SME_APPROVAL_NEEDED
        # elif last_action_taken == settings.CREDIT_CONTRACT_SME_APPROVED:
        #     return settings.CREDIT_PAYMENT_VIEW
        else:
            return settings.REQUEST_NO_ACTION_NEEDED

    elif current_user == settings.SME["name_value"]:
        if last_action_taken == settings.CREDIT_CONTRACT_ADMIN_SIGNED:
            return settings.CREDIT_CONTRACT_SME_APPROVAL_NEEDED
        else:
            return settings.REQUEST_NO_ACTION_NEEDED
    else:
        return settings.REQUEST_NO_ACTION_NEEDED


def check_update_credit(user_object, new_credit):
    """
    Function for checking the new credit amount change

    :param user_object: user instance
    :param new_credit: new credit amount added
    :return: [status, return_message]
    """
    # Currently check if the new credit is higher than the current amount
    if float(new_credit) >= user_object.credit_limit:
        return [True, None]
    else:
        return [False, "New credit amount is less than the current credit amount"]


def check_admin_payment_status(fund_invoice_id):
    """
    Function for checking if admin has added first installment to supplier and supplier has acknowledged

    :param fund_invoice_id: id of fund invoice
    :return: [admin_payment_status, payment_acknowledged]
    """
    from transaction_app import models
    payment_object = models.PaymentModel.objects.filter(payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN,
                                                        fund_invoice=fund_invoice_id, term_order=1)
    if payment_object.exists():
        # Admin has paid at least one installment to supplier
        admin_payment_status = True
        # No need for check for status or acknowledgement
        # if payment_object.filter(acknowledgement_completed=True).exists():
        #     # Acknowledgement of the first installment is completed
        #     payment_acknowledged = True
        # else:
        #     payment_acknowledged = False
        payment_acknowledged = True
        return [admin_payment_status, payment_acknowledged]
    else:
        return [False, False]


def get_payment_balance_amount(fund_invoice_object, payment_type, paying_amount=None):
    """
    Function for getting the balance amount to be paid against a user (Supplier, Factoring company, SME)

    :param paying_amount: amount added by the user
    :param payment_type: type of payment
    :param fund_invoice_object: fund invoice instance
    :return: [balance_status, error_msg, balance_amount]
    """
    from transaction_app import models
    payment_object = fund_invoice_object.payment_fund_invoice.all().filter(payment_type=payment_type). \
        aggregate(Sum("paying_amount"))
    if payment_object['paying_amount__sum']:
        paid_amount = float(payment_object["paying_amount__sum"])
    else:
        paid_amount = 0
    if int(payment_type) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
        tax_amount = fund_invoice_object.payment_fund_invoice.all().filter(payment_type=payment_type,
                                                                           payment_made_by__user_role=settings.SME_ROLE_VALUE). \
            aggregate(Sum("tax_amount"))
        if tax_amount['tax_amount__sum']:
            total_tax = float(tax_amount['tax_amount__sum'])
        else:
            total_tax = 0
        if (fund_invoice_object.contract_category == settings.MASTER_CONTRACT["number_value"]):
            balance_amount = round(float(fund_invoice_object.total_sales_amount), 3) - \
                             (paid_amount + total_tax)
        else:
            balance_amount = round(float(fund_invoice_object.contract_fund_invoice.all()[0].total_sales_amount), 3) - \
                             (paid_amount + total_tax)
    else:
        balance_amount = round(float(fund_invoice_object.invoice_total_amount), 3) - paid_amount

    if paying_amount:
        # if round(balance_amount, 3) <= 0:
        #     return [False, "Adding payment with balance amount to be paid is 0"]
        if round(paying_amount, 3) > round(balance_amount, 3):
            return [False, "Adding payment amount higher than the balance amount"]
        return [True]
    else:
        # Payment can be added as adhoc
        if balance_amount <= 0:
            return [True, "the balance amount to be paid is 0", 0]
        return [True, None, round(balance_amount, 3)]


def check_last_payment(fund_invoice_object, payment_type, input_term_order):
    """
    Check if the payment is added after the last payment is completed

    :param input_term_order: input term order
    :param payment_type: type of payment
    :param fund_invoice_object: fund invoice instance
    :return:
    """
    payment_object = fund_invoice_object.payment_fund_invoice.all().filter(payment_type=payment_type)
    if payment_object.exists():
        if payment_object[0].acknowledgement_completed:
            if int(input_term_order) == (int(payment_object[0].term_order) + 1):
                return [True]
            else:
                return [False, "Please check the term order added"]
        else:
            return [False, "Last payment's acknowledgement not completed yet"]
    else:
        if int(input_term_order) == 1:
            return [True]
        else:
            return [False, "Please check the term order added"]


# def check_sme_payment_amount(fund_invoice_object, amount_paying):
#     """
#     Check if the sme's payment is in accordance with payment term in contract
#     :param amount_paying: amount added by the sme user
#     :param fund_invoice_object: fund invoice instance
#     :return:
#     """
#     from transaction_app import models
#     payment_object = fund_invoice_object.payment_fund_invoice.all().filter(
#         payment_type=models.PAYMENT_TO_FACTORING_COMPANY_BY_SME)
#     payment_term_object = fund_invoice_object.contract_fund_invoice.all()[0].contract_type.payment_terms.terms.all()
#
#     if payment_object.exists():
#         term_status = False
#         for payment_term in payment_term_object:
#             if payment_term.terms_order == int(payment_object[0].term_order) + 1:
#                 term_status = True
#                 if payment_term.type == models.TERMS_TYPE_PERCENTAGE:
#                     term_amount = float(fund_invoice_object.contract_fund_invoice.all()[0].total_sales_amount) * \
#                                   (float(payment_term.value) / 100)
#                 elif payment_term.type == models.TERMS_TYPE_AMOUNT:
#                     term_amount = float(payment_term.value)
#                 if round(float(amount_paying), 3) == round(term_amount, 3):
#                     return [True]
#                 else:
#                     return [False, "Please enter the correct amount"]
#         if not term_status:
#             return [False, "Payment terms count completed"]
#     else:
#         for payment_term in payment_term_object:
#             if payment_term.terms_order == 1:
#                 if payment_term.type == models.TERMS_TYPE_PERCENTAGE:
#                     term_amount = float(fund_invoice_object.contract_fund_invoice.all()[0].total_sales_amount) * \
#                                   (float(payment_term.value) / 100)
#                 elif payment_term.type == models.TERMS_TYPE_AMOUNT:
#                     term_amount = float(payment_term.value)
#                 if round(float(amount_paying), 3) == round(term_amount, 3):
#                     return [True]
#                 else:
#                     return [False, "Please enter the correct amount"]


def list_payment_next_step(payment_object, user_role):
    """
        Function for getting the next step in payment
        :param payment_object: instance of payment object
        :param user_role: type of logged in user
        :return:
        """
    from transaction_app import models
    if payment_object.acknowledgement_completed:
        return settings.REQUEST_NO_ACTION_NEEDED
    else:
        if payment_object.payment_type == models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
            if user_role == settings.SUPPLIER["number_value"]:
                return settings.CREDIT_PAYMENT_ACKNOWLEDGMENT_NEEDED
            else:
                return settings.REQUEST_NO_ACTION_NEEDED

        elif payment_object.payment_type == models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY:
            if payment_object.payment_made_by.user_role != user_role:
                return settings.CREDIT_PAYMENT_ACKNOWLEDGMENT_NEEDED
            else:
                return settings.REQUEST_NO_ACTION_NEEDED
        else:
            return settings.REQUEST_NO_ACTION_NEEDED


def send_sme_review_email(subject, recipient_email, user_object, template_data, remarks, sme_company_name, bcc_email=[],
                          cc_email=[]):
    """
    Function for sending email for reviewing a sme user

    :param template_data: data for generating the pdf
    :param subject: subject of the email
    :param user_object: instance of user model
    :param recipient_email: list of recipient email ids
    :return:
    """
    # Creating pdf and html file
    from registration.serializers import UserDetailSerializers
    from contact_app.serializers import LeadsModelSerializers
    from contact_app.models import LeadsModel

    template_data_values = UserDetailSerializers(user_object.on_boarding_details).data
    lead_object = LeadsModelSerializers(instance=LeadsModel.objects.get(
        sign_up_email=user_object.email)).data
    template_data_values['country_name'] = lead_object['company_registered_in']
    template = Template(template_data)
    html_body = template.render(template_data_values)
    pdf_path = f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/" \
               f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/" \
               f"{settings.ON_BOARDING_SME_PDF_NAME}"

    pdfkit.from_string(html_body, pdf_path)

    file_size = os.path.getsize(f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/"
                                f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/"
                                f"{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}.zip")
    if (file_size / 1024 ** 2) < 10:
        message = render_to_string('registration/user_review.html', {'remarks': remarks,
                                                                     'logo_path': settings.BACKEND_URL[
                                                                                  :-1] + settings.MEDIA_URL + 'logo/',
                                                                     'sme_company_name': sme_company_name})
        email = EmailMessage(subject, message, settings.EMAIL_DEFAULT_EMAIL, recipient_email, bcc=bcc_email,
                             cc=cc_email)
        email.attach_file(f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/"
                          f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/"
                          f"{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}.zip")
        email.attach_file(f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/"
                          f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/"
                          f"{settings.ON_BOARDING_SME_PDF_NAME}")
        email.content_subtype = "html"
        email.send()
    else:
        zip_file_url = f"{settings.BACKEND_URL}{settings.MEDIA_URL}{settings.ON_BOARDING_DATA_BASE_PATH}/" \
                       f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/" \
                       f"{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}.zip"
        message = render_to_string('registration/user_review.html', {'zip_file_url': zip_file_url, 'remarks': remarks,
                                                                     'logo_path': settings.BACKEND_URL[
                                                                                  :-1] + settings.MEDIA_URL + 'logo/',
                                                                     'sme_company_name': sme_company_name})
        email = EmailMessage(subject, message, settings.EMAIL_DEFAULT_EMAIL, recipient_email, bcc=bcc_email,
                             cc=cc_email)
        email.attach_file(f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/"
                          f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/"
                          f"{settings.ON_BOARDING_SME_PDF_NAME}")
        email.content_subtype = "html"
        email.send()

    # Deleting the pdf and html file
    os.remove(pdf_path)


def generate_sme_zip_file(user_email):
    """
    Function for creating a zip file and pdf file of on board data

    :param user_email: email of user
    :return:
    """
    # Creating zip file
    user_object = User.objects.get(email=user_email)
    file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/{settings.ON_BOARDING_DATA_FILE_PATH}/'
    zip_file_path = f"{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/" \
                    f"{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}"
    onboard_path = f"{settings.MEDIA_ROOT}/{file_path}"
    shutil.make_archive(zip_file_path, 'zip', onboard_path)


def user_list_next_step(user_object, logged_in_user):
    """
    Function to list (user listing) the next actions of a user

    :param user_object: instance of the user model
    :param logged_in_user: logged in user data
    :return: next action
    """
    from registration import models
    from transaction_app.models import MasterContractStatusModel
    from contact_app.models import LeadsModel

    if logged_in_user.user_role == settings.ADMIN["number_value"]:
        if user_object.user_role == settings.SME["number_value"]:
            if user_object.on_board_status in [models.ON_BOARD_USER_CREATED, models.ON_BOARD_PASSWORD_SET]:
                return settings.SME_ONBOARD
            elif user_object.on_board_status == models.ON_BOARD_IN_PROGRESS:
                leads_obj = LeadsModel.objects.get(sign_up_email=user_object.email)
                if leads_obj.sync_status in [settings.SYNC_COMPLETED, settings.NO_SYNC]:
                    return settings.USER_REVIEW_PENDING
                else:
                    return settings.USER_NO_ACTION_NEEDED
            elif user_object.on_board_status == models.ON_BOARD_USER_REVIEWED:
                return settings.USER_ACTIVATION_PENDING
            elif user_object.on_board_status == models.ON_BOARD_COMPLETED:
                if user_object.master_contract is None:
                    return settings.CREDIT_ADMIN_CREATE_MASTER_CONTRACT
                else:
                    master_contract_status = MasterContractStatusModel.objects.filter(
                        contract=user_object.master_contract).first().action_taken
                    if master_contract_status == settings.CREDIT_CONTRACT_ADMIN_CREATED:
                        return settings.CREDIT_CONTRACT_ADMIN_TO_SIGN
                    else:
                        return settings.REQUEST_NO_ACTION_NEEDED
            else:
                return settings.REQUEST_NO_ACTION_NEEDED
        elif user_object.user_role == settings.SUPPLIER["number_value"]:
            if user_object.on_board_status in [ON_BOARD_USER_CREATED, ON_BOARD_PASSWORD_SET]:
                return settings.SUPPLIER_ONBOARD
            elif user_object.on_board_status == models.ON_BOARD_IN_PROGRESS:
                return settings.USER_ACTIVATION_PENDING
            else:
                return settings.USER_NO_ACTION_NEEDED
        else:
            return settings.USER_NO_ACTION_NEEDED
    else:
        return settings.USER_NO_ACTION_NEEDED


def docu_sign_make_envelope(signer_email, signer_name, by_sme, contract_id, contract_file_path=None,
                            master_contract=None):
    """
    Function to make envelope (doc) for user to sign

    :param contract_file_path: getting initial contract file
    :param by_sme: True/False if signing needs to be done by sme
    :param signer_email: email of the signer
    :param signer_name: name of the signer
    :return: envelope url and id
    """
    if not signer_name:
        signer_name = "Test Name"
    with open(os.path.join(f'{settings.MEDIA_ROOT}/{contract_file_path}'), "rb") as file:
        content_bytes = file.read()
    detail_object = User.objects.get(email=signer_email)
    if detail_object.on_boarding_details is not None:
        company_name_value = detail_object.on_boarding_details.company_name
    else:
        company_name_value = "Test company"

    if by_sme:
        if master_contract:
            sign_here = SignHere(document_id='1', recipient_id='1', tab_label='Sign Here',
                                 anchor_string='//sme_signature_1//',
                                 anchor_x_offset='6', anchor_y_offset='0', scale_value='90')
            sign_date = DateSigned(document_id='1', recipient_id='1', tab_label='Date',
                                   value=datetime.today().strftime('%d/%m/%Y'), tab_id='date',
                                   anchor_string='//date_sign_2//', anchor_x_offset='1',
                                   anchor_y_offset='-5',
                                   width='100')
            attorney_name = Text(document_id='1', recipient_id='1', tab_label='Attorney Name', tab_id='attorney_name',
                                 anchor_string='//name_of_attorney//', anchor_x_offset='6', anchor_y_offset='0',
                                 width='100')
            attorney_sign_here = SignHere(document_id='1', recipient_id='1', tab_label='Attorney Sign',
                                          anchor_string='//sign_of_attorney//',
                                          anchor_x_offset='6', anchor_y_offset='0', scale_value='90')
            presence_of_1 = Text(document_id='1', recipient_id='1', tab_label='Presence of user',
                                 tab_id='presence_of_1',
                                 anchor_string='//in_presence_of//', anchor_x_offset='1', anchor_y_offset='-5',
                                 width='100')
            witness_sign_here = SignHere(document_id='1', recipient_id='1', tab_label='Witness Sign',
                                         tab_id="witness_sign_here",
                                         anchor_string='//witness_sign_1//',
                                         anchor_x_offset='7', anchor_y_offset='15', scale_value='50')
            witness_name_1 = Text(document_id='1', recipient_id='1', tab_label='Witness Name', tab_id='witness_name_1',
                                  anchor_string='//witness_full_name_1//', anchor_x_offset='1', anchor_y_offset='-5',
                                  width='100')
            witness_address = Text(document_id='1', recipient_id='1', tab_label='Witness Address',
                                   tab_id='witness_address',
                                   anchor_string='//witness_address//', anchor_x_offset='1', anchor_y_offset='-5',
                                   width='100')
            witness_address_2 = Text(document_id='1', recipient_id='1', tab_label='Witness Address',
                                     tab_id='witness_address',
                                     anchor_string='//witness_address_2//', anchor_x_offset='1', anchor_y_offset='-5',
                                     width='100')
            witness_occupation = Text(document_id='1', recipient_id='1', tab_label='Witness occupation',
                                      tab_id='witness_occupation',
                                      anchor_string='//witness_occupation//', anchor_x_offset='1', anchor_y_offset='-5',
                                      width='100')
            witness_occupation_2 = Text(document_id='1', recipient_id='1', tab_label='Witness occupation',
                                        tab_id='witness_occupation',
                                        anchor_string='//witness_occupation_2//', anchor_x_offset='1',
                                        anchor_y_offset='-5',
                                        width='100')
            on_behalf_of_sme = Text(document_id='1', recipient_id='1', tab_label='On behalf of SME',
                                    tab_id='on_behalf_of_sme',
                                    anchor_string='//on_behalf_of_sme//', anchor_x_offset='1', anchor_y_offset='-5',
                                    width='100')
            presence_of_2 = Text(document_id='1', recipient_id='1', tab_label='Presence of user',
                                 tab_id='presence_of_1',
                                 anchor_string='//in_presence_of_2//', anchor_x_offset='1', anchor_y_offset='-5',
                                 width='100')
            witness_sign_2 = SignHere(document_id='1', recipient_id='1', tab_label='Witness Sign',
                                      tab_id='witness_sign_here',
                                      anchor_string='//witness_sign_2//', anchor_x_offset='5', anchor_y_offset='13',
                                      scale_value='50')
            witness_name_2 = Text(document_id='1', recipient_id='1', tab_label='Witness Name', tab_id='witness_name_1',
                                  anchor_string='//witness_name_2//', anchor_x_offset='1', anchor_y_offset='-5',
                                  width='100')
            signer_tab = Tabs(sign_here_tabs=[sign_here, witness_sign_2, attorney_sign_here, witness_sign_here],
                              text_tabs=[sign_date, witness_name_2, presence_of_2, on_behalf_of_sme,
                                         witness_occupation, witness_address, witness_name_1, attorney_name,
                                         presence_of_1, witness_address_2,
                                         witness_occupation_2])
        else:
            sign_here = SignHere(document_id='1', recipient_id='1', tab_label='Sign Here',
                                 anchor_string='//sme_sign//',
                                 anchor_x_offset='8', anchor_y_offset='15', scale_value='50')
            sign_date = DateSigned(document_id='1', recipient_id='1', tab_label='Date',
                                   value=datetime.today().strftime('%d/%m/%Y'), tab_id='date',
                                   anchor_string='//sme_date//', anchor_x_offset='1', anchor_y_offset='-3',
                                   width='100')
            company_name = Text(document_id='1', recipient_id='1', tab_label='Company Name', tab_id='company_name',
                                anchor_string='//sme_company//', anchor_x_offset='1', anchor_y_offset='-3', width='100',
                                value=company_name_value, locked=False)
            name = Text(document_id='1', recipient_id='1', tab_label='Name', tab_id='name',
                        anchor_string='//sme_name//',
                        anchor_x_offset='1', anchor_y_offset='-3', width='100', value=signer_name, locked=False)
            title = Text(document_id='1', recipient_id='1', tab_label='Title', tab_id='title',
                         anchor_string='//sme_title//', anchor_x_offset='1', anchor_y_offset='-3', width='100')
            signer_tab = Tabs(sign_here_tabs=[sign_here], text_tabs=[company_name, sign_date, name, title])

    else:
        if master_contract:
            sign_here = SignHere(document_id='1', recipient_id='1', tab_label='Sign Here',
                                 anchor_string='//admin_signature//',
                                 anchor_x_offset='5', anchor_y_offset='0', scale_value='90')
            sign_date = DateSigned(document_id='1', recipient_id='1', tab_label='Date',
                                   value=datetime.today().strftime('%d/%m/%Y'), tab_id='date',
                                   anchor_string='//date_of_signing_1//', anchor_x_offset='1',
                                   anchor_y_offset='-5',
                                   width='100')
            name = Text(document_id='1', recipient_id='1', tab_label='Name', tab_id='company_name',
                        anchor_string='//admin_name//', anchor_x_offset='1', anchor_y_offset='-5',
                        width='100', value=signer_name, locked=False)
            signer_tab = Tabs(sign_here_tabs=[sign_here], text_tabs=[sign_date, name])
        else:
            sign_here = SignHere(document_id='1', recipient_id='1', tab_label='Sign Here',
                                 anchor_string='//admin_sign//',
                                 anchor_x_offset='8', anchor_y_offset='15', scale_value='50')
            sign_date = DateSigned(document_id='1', recipient_id='1', tab_label='Date',
                                   value=datetime.today().strftime('%d/%m/%Y'), tab_id='date',
                                   anchor_string='//admin_date//', anchor_x_offset='1', anchor_y_offset='-3',
                                   width='100')
            name = Text(document_id='1', recipient_id='1', tab_label='Name', tab_id='company_name',
                        anchor_string='//admin_name//', anchor_x_offset='1', anchor_y_offset='-5', width='100',
                        value=signer_name, locked=False)
            title = Text(document_id='1', recipient_id='1', tab_label='Title',
                         tab_id='title', anchor_string='//admin_title//', anchor_x_offset='1', anchor_y_offset='-3',
                         width='100')
            signer_tab = Tabs(sign_here_tabs=[sign_here], text_tabs=[sign_date, name, title])

    # Create the document model
    base64_file_content = base64.b64encode(content_bytes).decode('ascii')
    document = Document(document_base64=base64_file_content, name='sign_doc', file_extension='pdf', document_id='1')
    # Create the signer recipient model
    signer = Signer(email=signer_email, name=signer_name, recipient_id="1", routing_order="1",
                    client_user_id=settings.DOCU_SIGN_CLIENT_USER_ID, tabs=signer_tab)
    # Next, create the top level envelope definition and populate it.
    envelope_definition = EnvelopeDefinition(email_subject="Please sign this document", documents=[document],
                                             recipients=Recipients(signers=[signer]), status="sent")
    # Generate token
    jwt_token = get_docu_sign_jwt_token()

    # Call Envelopes::create API method
    api_client = ApiClient()
    api_client.host = settings.DOCU_SIGN_HOST_URL
    api_client.set_default_header(header_name="Authorization", header_value=f"Bearer {jwt_token['access_token']}")

    envelope_api = EnvelopesApi(api_client)
    results = envelope_api.create_envelope(account_id=settings.DOCU_SIGN_ACCOUNT_ID,
                                           envelope_definition=envelope_definition)

    envelope_id = results.envelope_id
    # Create the Recipient View request object
    recipient_view_request = RecipientViewRequest(authentication_method='email',
                                                  client_user_id=settings.DOCU_SIGN_CLIENT_USER_ID, recipient_id='1',
                                                  return_url=f"{settings.DOCU_SIGN_REDIRECT_URL}{contract_id}",
                                                  user_name=signer_name,
                                                  email=signer_email)
    # Obtain the recipient_view_url for the signing ceremony
    results = envelope_api.create_recipient_view(settings.DOCU_SIGN_ACCOUNT_ID, envelope_id,
                                                 recipient_view_request=recipient_view_request)
    return {'envelope_id': envelope_id, 'redirect_url': results.url}


def get_docu_sign_jwt_token():
    """
    Function for getting the docu sign token

    :return:
    """
    with open(settings.DOCU_SIGN_PRIVATE_KEY_PATH, "rb") as key_file:
        private_key_bytes = crypto_serialization.load_pem_private_key(key_file.read(), password=None)

    if not private_key_bytes:
        raise ArgumentException("Private key not supplied or is invalid!")
    if not settings.DOCU_SIGN_CLIENT_USER_ID:
        raise ArgumentException("User Id not supplied or is invalid!")
    if not settings.DOCU_SIGN_AUTH_URL:
        raise ArgumentException("oAuthBasePath cannot be empty")
    now = math.floor(time())
    later = now + 4000
    claim = {"iss": settings.DOCU_SIGN_CLIENT_ID, "sub": settings.DOCU_SIGN_CLIENT_USER_ID,
             "aud": settings.DOCU_SIGN_AUTH_URL, "iat": now, "exp": later,
             "scope": "signature impersonation"}
    token = jwt.encode(payload=claim, key=private_key_bytes, algorithm='RS256').decode("utf-8")
    response = requests.post(settings.DOCU_SIGN_AUTH_BASE_URL,
                             data={'grant_type': settings.DOCU_SIGN_AUTH_GRANT_TYPE, 'assertion': token},
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    response_data = response.json()
    return response_data


def get_docu_sign_doc(envelope_id, signed_by, fund_invoice_object=None, user_object=None):
    """
    Function for getting the signed doc

    :param signed_by: signed by user
    :param envelope_id: id of envelope
    :param fund_invoice_object: instance of fund invoice
    :return:
    """
    from transaction_app import models
    # Generate token
    jwt_token = get_docu_sign_jwt_token()

    doc_status_url = f"{settings.DOCU_SIGN_HOST_URL}/v2.1/accounts/{settings.DOCU_SIGN_ACCOUNT_ID}/envelopes/" \
                     f"{envelope_id}"
    status_response = requests.get(doc_status_url, headers={'Authorization': 'Bearer ' + jwt_token['access_token']})
    base_path = None
    response = None
    file_name = None
    file_type = None
    if status_response.json()['status'] == 'completed':
        test_url = f"{settings.DOCU_SIGN_HOST_URL}/v2.1/accounts/{settings.DOCU_SIGN_ACCOUNT_ID}/envelopes/{envelope_id}/" \
                   f"documents/1"
        response = requests.get(test_url, headers={'Authorization': 'Bearer ' + jwt_token['access_token']})

        if fund_invoice_object is not None:
            base_path = f'{settings.FUND_INVOICE_DATA}/{str(fund_invoice_object.id)}/{settings.SIGNED_CONTRACT_FILES}/'
            if signed_by.user_role == settings.SME['number_value']:
                file_name = settings.CONTRACT_FILE_SME_SIGNED_NAME
                file_type = models.SME_SIGNED_CONTRACT
                # Taking backup of old signed file
                signed_contract_object = fund_invoice_object.contract_fund_invoice.all()[0].signed_contract_file.filter(
                    contract_doc_type=models.SME_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_CREATED)
                if signed_contract_object.exists():
                    backup_name = f"{file_name.split('.')[0]}_{str(math.floor(time()))}.pdf"
                    os.rename(f'{settings.MEDIA_ROOT}/{base_path}{file_name}',
                              f'{settings.MEDIA_ROOT}/{base_path}{backup_name}')
                    signed_contract_object.update(file_path=f'{base_path}{backup_name}',
                                                  file_status=models.SIGNED_CONTRACT_DISABLED)
            else:
                file_name = settings.CONTRACT_FILE_ADMIN_SIGNED_NAME
                file_type = models.ADMIN_SIGNED_CONTRACT
                # Taking backup of old signed file
                signed_contract_object = fund_invoice_object.contract_fund_invoice.all()[0].signed_contract_file.filter(
                    contract_doc_type=models.ADMIN_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_CREATED)
                if signed_contract_object.exists():
                    backup_name = f"{file_name.split('.')[0]}_{str(math.floor(time()))}.pdf"
                    os.rename(f'{settings.MEDIA_ROOT}/{base_path}{file_name}',
                              f'{settings.MEDIA_ROOT}/{base_path}{backup_name}')
                    signed_contract_object.update(file_path=f'{base_path}{backup_name}',
                                                  file_status=models.SIGNED_CONTRACT_DISABLED)

            with open(os.path.join(f'{settings.MEDIA_ROOT}/{base_path}{file_name}'), "wb") as file:
                file.write(response.content)
            contract_file_object = models.SignedContractFilesModel.objects.create(contract=fund_invoice_object.
                                                                                  contract_fund_invoice.all()[0],
                                                                                  contract_doc_type=file_type,
                                                                                  action_by=signed_by,
                                                                                  file_path=f'{base_path}{file_name}',
                                                                                  file_status=models.SIGNED_CONTRACT_CREATED)
        else:
            base_path = f'{settings.USER_DATA}/{str(user_object.id)}/{settings.SIGNED_CONTRACT_FILES}/'
            if signed_by.user_role == settings.SME['number_value']:
                file_name = settings.MASTER_CONTRACT_SME_SIGNED_NAME
                file_type = models.SME_SIGNED_CONTRACT
                # Taking backup of old signed file
                signed_contract_object = models.SignedContractFilesModel.objects.filter(
                    contract=user_object.master_contract,
                    contract_doc_type=models.SME_SIGNED_CONTRACT,
                    file_status=models.SIGNED_CONTRACT_CREATED)
                if signed_contract_object.exists():
                    backup_name = f"{file_name.split('.')[0]}_{str(math.floor(time()))}.pdf"
                    os.rename(f'{settings.MEDIA_ROOT}/{base_path}{file_name}',
                              f'{settings.MEDIA_ROOT}/{base_path}{backup_name}')
                    signed_contract_object.update(file_path=f'{base_path}{backup_name}',
                                                  file_status=models.SIGNED_CONTRACT_DISABLED)
            else:
                file_name = settings.MASTER_CONTRACT_ADMIN_SIGNED_NAME
                file_type = models.ADMIN_SIGNED_CONTRACT
                # Taking backup of old signed file
                signed_contract_object = models.SignedContractFilesModel.objects.filter(
                    contract=user_object.master_contract,
                    contract_doc_type=models.ADMIN_SIGNED_CONTRACT,
                    file_status=models.SIGNED_CONTRACT_CREATED)
                if signed_contract_object.exists():
                    backup_name = f"{file_name.split('.')[0]}_{str(math.floor(time()))}.pdf"
                    os.rename(f'{settings.MEDIA_ROOT}/{base_path}{file_name}',
                              f'{settings.MEDIA_ROOT}/{base_path}{backup_name}')
                    signed_contract_object.update(file_path=f'{base_path}{backup_name}',
                                                  file_status=models.SIGNED_CONTRACT_DISABLED)

            with open(os.path.join(f'{settings.MEDIA_ROOT}/{base_path}{file_name}'), "wb") as file:
                file.write(response.content)
            contract_file_object = models.SignedContractFilesModel.objects.create(contract=user_object.master_contract,
                                                                                  action_by=signed_by,
                                                                                  contract_doc_type=file_type,
                                                                                  file_path=f'{base_path}{file_name}',
                                                                                  file_status=models.SIGNED_CONTRACT_CREATED)

        contract_file_object.save()
        # Response body "data" updated for FE requirements
        return {"status": True, "data": [{"file": f'{settings.MEDIA_URL}{contract_file_object.file_path}',
                                          "contract_doc_type": contract_file_object.get_contract_doc_type_display()}]}
    else:
        return {"status": False, "data": {"error_message": 'Document not yet signed, please sign the document'}}


def get_payment_warning_message(warning_issues):
    """
    Function for generating warning message

    :param warning_issues: List of warning strings ["term_missing", "balance_nil", "payment_status_missing",
    "payment_acknowledgement_missing", "supplier_payment_missing", "supplier_payment_acknowledgement_missing",
    "sme_payment_missing", "sme_payment_acknowledgement_missing", "shipment_missing", "payment_balance_issue",
    "term_payment_issue"]
    :return: [warning_message, is_adhoc]
    """
    warning_message_list = list()
    is_adhoc = False
    # Trying to add payment after valid payment term is finished
    if "term_missing" in warning_issues:
        warning_message_list.append("No valid payment term remaining")
        is_adhoc = True
    # Trying to add payment when balance to be paid is 0
    if "balance_nil" in warning_issues:
        warning_message_list.append("Balance amount to be paid is 0")
        is_adhoc = True

    # No need for check for status or acknowledgement
    # Trying to add payment when last payment status is not completed
    # if "payment_status_missing" in warning_issues:
    #     warning_message_list.append("Last payment status is not yet updated")
    # Trying to add payment when last payment is not yet acknowledged
    # else:
    #     if "payment_acknowledgement_missing" in warning_issues:
    #         warning_message_list.append("Last payment added is not yet acknowledged")
    # Not needed

    # Trying to add payment when initial supplier payment is not yet added
    if "supplier_payment_missing" in warning_issues:
        warning_message_list.append("Initial payment to supplier not yet added")
    # Trying to add payment when initial supplier payment is not yet acknowledged
    else:
        if "supplier_payment_acknowledgement_missing" in warning_issues:
            warning_message_list.append("Initial payment to supplier not yet acknowledged")
    # Trying to add payment when initial sme payment is not yet added
    if "sme_payment_missing" in warning_issues:
        warning_message_list.append("Initial payment by SME is not yet added")
    # Trying to add payment when initial sme payment is not yet acknowledged
    else:
        if "sme_payment_acknowledgement_missing" in warning_issues:
            warning_message_list.append("Initial payment by SME is not yet acknowledged")
    # Trying to add payment to supplier without adding shipment
    if "shipment_missing" in warning_issues:
        warning_message_list.append("Shipment not yet added")
    # Trying to add payment more than the balance amount
    if "payment_balance_issue" in warning_issues:
        warning_message_list.append("Adding payment amount higher than the balance amount")
    # Trying to add payment different from term amount
    if "term_payment_issue" in warning_issues:
        warning_message_list.append("Payment added different from the payable term amount")
    if is_adhoc:
        warning_message_list.append("Payment will be added as adhoc")
    return [warning_message_list, is_adhoc]


def check_sme_payment_status(fund_invoice_id):
    """
    Function for checking if sme has added first installment to factoring company and acknowledgment is complete

    :param fund_invoice_id: id of fund invoice
    :return: [admin_payment_status, payment_acknowledged]
    """
    from transaction_app import models
    payment_object = models.PaymentModel.objects.filter(payment_type=models.PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                        fund_invoice=fund_invoice_id, term_order=1)
    if payment_object.exists():
        # Admin has paid at least one installment to supplier
        sme_payment_status = True
        # No need for check for status or acknowledgement
        # if payment_object.filter(acknowledgement_completed=True).exists():
        #     # Acknowledgement of the first installment is completed
        #     payment_acknowledged = True
        # else:
        #     payment_acknowledged = False
        payment_acknowledged = True
        return [sme_payment_status, payment_acknowledged]
    else:
        return [False, False]


def payment_to_supplier_details(fund_invoice_object, api_request):
    """
    Function for getting payment to supplier details

    :param api_request: request from api
    :param fund_invoice_object: invoice instance
    :return: payment details
    """
    from transaction_app import models, serializers

    payment_object = fund_invoice_object.payment_fund_invoice.filter(
        payment_made_by__user_role=settings.ADMIN_ROLE_VALUE, payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN)
    warning_issues = list()
    output_dict = dict()
    balance_amount = get_payment_balance_amount(fund_invoice_object, models.PAYMENT_TO_SUPPLIER_BY_ADMIN)
    output_dict["balance_amount"] = balance_amount[2]
    if payment_object.exists():
        serializer_data = serializers.PaymentModelSerializer(payment_object[0], context={'request': api_request}).data
        # Checking if balance amount to be paid is 0
        if not output_dict["balance_amount"]:
            warning_issues.append("balance_nil")
        # Checking if the user has updated the last payment status
        # if serializer_data["next_step"] == settings.CREDIT_PAYMENT_STATUS_UPDATE:
        #     warning_issues.append("payment_status_missing")
        # Checking if the last payment added is acknowledged or not
        if not serializer_data['acknowledgement_completed']:
            warning_issues.append("payment_acknowledgement_missing")
        output_dict["term_order"] = int(payment_object[0].term_order) + 1
    else:
        output_dict["term_order"] = 1

    payment_term_object = fund_invoice_object.supplier_term.supplier_terms.filter(terms_order=output_dict["term_order"])
    # Checking for the next payment term, if no payment term is present, added as adhoc
    if payment_term_object.exists():
        output_dict["terms"] = serializers.SupplierTermsModelSerializer(payment_term_object[0]).data
        if payment_term_object[0].value_type == models.TERMS_TYPE_PERCENTAGE:
            term_amount = float(
                fund_invoice_object.invoice_total_amount) * (float(payment_term_object[0].value) / 100)
        elif payment_term_object[0].value_type == models.TERMS_TYPE_AMOUNT:
            term_amount = float(payment_term_object[0].value)
        # Check for the before shipment constraint
        if not payment_term_object[0].before_shipment:
            if not fund_invoice_object.fund_invoice_status.filter(Q(action_taken=
                                                                    settings.CREDIT_SHIPMENT_SUPPLIER_CREATED) |
                                                                  Q(action_taken=
                                                                    settings.CREDIT_SHIPMENT_SME_CREATED)).exists():
                warning_issues.append("shipment_missing")
        output_dict["terms"]["term_amount"] = round(term_amount, 3)
    else:
        warning_issues.append("term_missing")
        output_dict["term_order"] = int(payment_object[0].term_order) + 1
    # Admin user can add new payment
    output_dict["invoice_number"] = fund_invoice_object.invoice_number
    output_dict["can_create_payment"] = True
    output_dict["next_step"] = settings.CREDIT_ADD_PAYMENT
    warning_adhoc = get_payment_warning_message(warning_issues)
    output_dict["warning_message"] = warning_adhoc[0]
    output_dict["is_adhoc"] = warning_adhoc[1]
    return output_dict


def payment_to_admin_details(fund_invoice_object, api_request):
    """
    Function for getting payment to admin details

    :param api_request: request from api
    :param fund_invoice_object: invoice instance
    :return: payment details
    """
    from transaction_app import models, serializers
    warning_issues = list()
    output_dict = dict()

    # No need for check for status or acknowledgement, commented in check_admin_payment_status function
    # Checking if admin has paid at least one installment to supplier
    admin_payment_status = check_admin_payment_status(fund_invoice_object.id)
    if not admin_payment_status[0]:
        warning_issues.append("supplier_payment_missing")
    if not admin_payment_status[1]:
        warning_issues.append("supplier_payment_acknowledgement_missing")

    # No need for check for status or acknowledgement, commented in check_sme_payment_status function
    # Checking if sme has paid at least one installment to factoring company
    sme_payment_status = check_sme_payment_status(fund_invoice_object.id)
    if not sme_payment_status[0]:
        warning_issues.append("sme_payment_missing")
    if not sme_payment_status[1]:
        warning_issues.append("sme_payment_acknowledgement_missing")

    payment_object = fund_invoice_object.payment_fund_invoice.filter(
        payment_type=models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY)
    if payment_object.exists():
        serializer_data = serializers.PaymentModelSerializer(payment_object[0],
                                                             context={'request': api_request}).data
        # Checking if the user has updated the last payment status
        # if serializer_data["next_step"] == settings.CREDIT_PAYMENT_STATUS_UPDATE:
        #     warning_issues.append("payment_status_missing")
        # Checking if the last payment added is acknowledged or not
        if not serializer_data['acknowledgement_completed']:
            warning_issues.append("payment_acknowledgement_missing")
        output_dict["term_order"] = int(payment_object[0].term_order) + 1
    else:
        output_dict["term_order"] = 1
    # Admin/Factor user can add new payment
    output_dict["can_create_payment"] = True
    output_dict["next_step"] = settings.CREDIT_ADD_PAYMENT
    warning_adhoc = get_payment_warning_message(warning_issues)
    output_dict["warning_message"] = warning_adhoc[0]
    output_dict["is_adhoc"] = warning_adhoc[1]
    output_dict["invoice_number"] = fund_invoice_object.invoice_number

    return output_dict


def payment_to_factor_details(fund_invoice_object, api_request):
    """
    Function for getting payment to factor by sme details

    :param api_request: request from api
    :param fund_invoice_object: invoice instance
    :return: payment details
    """
    from transaction_app import models, serializers
    warning_issues = list()
    output_dict = dict()
    balance_amount = get_payment_balance_amount(fund_invoice_object, models.PAYMENT_TO_FACTORING_COMPANY_BY_SME)
    output_dict["balance_amount"] = balance_amount[2]
    output_dict["invoice_number"] = fund_invoice_object.invoice_number

    # No need for check for status or acknowledgement, commented in check_admin_payment_status function
    # Checking if admin has paid at least one installment to supplier
    admin_payment_status = check_admin_payment_status(fund_invoice_object.id)
    if not admin_payment_status[0]:
        warning_issues.append("supplier_payment_missing")
    if not admin_payment_status[1]:
        warning_issues.append("supplier_payment_acknowledgement_missing")
    payment_object = fund_invoice_object.payment_fund_invoice.filter(payment_made_by__user_role=settings.
                                                                     SME_ROLE_VALUE, payment_type=models.
                                                                     PAYMENT_TO_FACTORING_COMPANY_BY_SME)
    # Checking if at least one payment is added
    if payment_object.exists():
        serializer_data = serializers.PaymentModelSerializer(payment_object[0], context={'request': api_request}).data
        # Checking if balance amount to be paid is 0
        if not output_dict["balance_amount"]:
            warning_issues.append("balance_nil")
        # Checking if the user has updated the last payment status
        # if serializer_data["next_step"] == settings.CREDIT_PAYMENT_STATUS_UPDATE:
        #     warning_issues.append("payment_status_missing")
        # Checking if the last payment added is acknowledged or not
        # if not serializer_data['acknowledgement_completed']:
        #     warning_issues.append("payment_acknowledgement_missing")
        output_dict["term_order"] = int(payment_object[0].term_order) + 1
    else:
        output_dict["term_order"] = 1

    # Checking the type of sme payment term
    if fund_invoice_object.contract_fund_invoice.first() is None:
        contract_fund_invoice_obj = fund_invoice_object.sme.master_contract
    else:
        contract_fund_invoice_obj = fund_invoice_object.contract_fund_invoice.first()
    amount_term_object = contract_fund_invoice_obj.contract_type. \
        payment_terms.sme_amount_terms.all()
    if amount_term_object.exists():
        # Checking for the next payment term, if no payment term is present added as adhoc
        if amount_term_object.filter(terms_order=output_dict["term_order"]).exists():
            payment_term = amount_term_object.filter(terms_order=output_dict["term_order"])[0]
            output_dict["terms"] = serializers.SmeTermsAmountModelSerializer(payment_term).data
            if payment_term.type == models.TERMS_TYPE_PERCENTAGE:
                if fund_invoice_object.contract_category == settings.MASTER_CONTRACT["number_value"]:
                    term_amount = float(
                        fund_invoice_object.total_sales_amount) * \
                                  (float(payment_term.value) / 100)
                else:
                    term_amount = float(
                        fund_invoice_object.contract_fund_invoice.all()[0].total_sales_amount) * \
                                  (float(payment_term.value) / 100)
            elif payment_term.type == models.TERMS_TYPE_AMOUNT:
                term_amount = float(payment_term.value)
            output_dict["terms"]["term_amount"] = round(term_amount, 3)
        else:
            warning_issues.append("term_missing")
    else:
        installment_term_object = contract_fund_invoice_obj. \
            contract_type.payment_terms.sme_installment_terms.filter(units__gte=output_dict["term_order"])
        if installment_term_object.exists():
            equal_installment_object = installment_term_object.filter(equal_installments=True)
            if equal_installment_object.exists():
                output_dict["terms"] = serializers.SmeTermsInstallmentModelSerializer(installment_term_object[0]).data
                if fund_invoice_object.contract_category == settings.MASTER_CONTRACT["number_value"]:
                    output_dict["terms"]["term_amount"] = round(fund_invoice_object.
                                                                total_sales_amount / output_dict['terms']['units'], 3)
                else:
                    output_dict["terms"]["term_amount"] = round(fund_invoice_object.contract_fund_invoice.all()[0].
                                                                total_sales_amount / output_dict['terms']['units'], 3)
                output_dict["terms"]['terms_label'] = contract_fund_invoice_obj.contract_type. \
                    payment_terms.name
        else:
            warning_issues.append("term_missing")

    # SME user can add new payment
    output_dict["can_create_payment"] = True
    output_dict["next_step"] = settings.CREDIT_ADD_PAYMENT
    warning_adhoc = get_payment_warning_message(warning_issues)
    output_dict["warning_message"] = warning_adhoc[0]
    output_dict["is_adhoc"] = warning_adhoc[1]

    return output_dict


def get_shipment_warning_message(invoice_object, payment_object, terms):
    """
    Function for generating warning message
    :param invoice_object: instance of fund invoice object
    :param payment_object: instance of payment object
    :param terms: supplier terms
    :return: [warning_message]
    """
    from transaction_app import models
    warning_messages = []
    if terms is not None:
        if payment_object.exists():
            for term in terms:
                terms_payment_obj = payment_object.filter(term_order=term.terms_order)
                if not terms_payment_obj:
                    warning_messages.append(f'Payment term {term.terms_label} not completed')
                else:
                    payed_amount = terms_payment_obj[0].paying_amount
                    if term.value_type == models.TERMS_TYPE_PERCENTAGE:
                        term_amount = float(invoice_object.invoice_total_amount) * (float(term.value) / 100)
                    elif term.value_type == models.TERMS_TYPE_AMOUNT:
                        term_amount = float(term.value)
                    if round(float(payed_amount), 3) != round(term_amount, 3):
                        warning_messages.append(f'Incorrect payment amount for term {term.terms_label}')
        else:
            warning_messages.append("Payment to supplier not yet added")

    return warning_messages


def check_for_valid_payment_criteria(sme_terms):
    """
    Function for checking if payment criteria is  valid

    :param sme_terms: list of terms added
    :return: response_data: [terms_valid_status, error_message]
    """
    from transaction_app import models
    days = 0
    for terms in sme_terms:
        if terms["criteria"] == models.TERMS_CRITERIA_DAYS_FROM_LAST_PAYMENT:
            if not days:
                return [False, "Please add a valid criteria"]
            else:
                days += terms["days"]
        if terms["criteria"] == models.TERMS_CRITERIA_DAYS_FROM_CONTRACT_SIGNATURE:
            if not days:
                days = terms["days"]
            else:
                if terms["days"] > days:
                    days = terms["days"]
                else:
                    return [False, "Please add payment term days greater than that of previous payment term"]
    return [True, None]


# def list_invoice_next_step(request_stage, current_user):
#     """
#     Function to list the next actions of a user
#     :param request_stage: last response status
#     :param current_user: viewing user role
#     :return: next action
#     """
#     if current_user == settings.ADMIN["name_value"]:
#         if request_stage == settings.CREDIT_INVOICE_SUPPLIER_APPROVED:
#             return settings.CREDIT_INVOICE_ADMIN_APPROVAL_NEEDED
#         elif request_stage == settings.CREDIT_INVOICE_SME_APPROVED:
#             return settings.CREDIT_INVOICE_ADMIN_APPROVAL_NEEDED
#         else:
#             return settings.REQUEST_NO_ACTION_NEEDED
#
#     elif current_user == settings.SUPPLIER["name_value"]:
#         if request_stage == settings.CREDIT_INVOICE_SME_UPLOADED:
#             return settings.CREDIT_INVOICE_SUPPLIER_APPROVAL_NEEDED
#         elif request_stage == settings.CREDIT_INVOICE_ADMIN_APPROVED:
#             return settings.CREDIT_INVOICE_ADMIN_APPROVED
#         elif request_stage == settings.CREDIT_INVOICE_SME_APPROVED:
#             return settings.CREDIT_INVOICE_SME_APPROVED
#         else:
#             return settings.REQUEST_NO_ACTION_NEEDED
#
#     elif current_user == settings.SME["name_value"]:
#         if request_stage == settings.CREDIT_INVOICE_SUPPLIER_UPLOADED:
#             return settings.CREDIT_INVOICE_SME_APPROVAL_NEEDED
#         elif request_stage == settings.CREDIT_INVOICE_SUPPLIER_APPROVED:
#             return settings.CREDIT_INVOICE_SUPPLIER_APPROVED
#         elif request_stage == settings.CREDIT_INVOICE_ADMIN_APPROVED:
#             return settings.CREDIT_INVOICE_ADMIN_APPROVED
#         else:
#             return settings.REQUEST_NO_ACTION_NEEDED

# def request_supplier_upload_invoice(subject, model_instance):
#     """
#     Function for sending email to supplier to upload invoice
#
#     :param subject: subject of the email
#     :param model_instance: model instance
#     :return:
#     """
#
#     message = render_to_string('transaction_app/request_supplier_upload_invoice.html',
#                                {'instance_data': model_instance})
#     send_email_utility(subject, message, model_instance.supplier.email, settings.EMAIL_HOST_USER)

def shipment_send_back_email(subject, id, recipient_email, remarks, recipient_name, sender_name):
    """
    Function for sending email when user reject the shipment

    :param subject: subject of the email
    :param id: fund invoice id
    :param recipient_email: email id of recipient
    :param remarks : remarks from sender
    :param recipient_name : recipent name
    :param sender_name : sender name
    :return:
    """

    message = render_to_string('transaction_app/shipment_sendback.html', {
        'reciever_name': recipient_name,
        'remarks': remarks,
        'sender_name': sender_name,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/',
        'login_link': f'{settings.FRONTEND_URL}{settings.SHIPMENT_SEND_BACK_URL}{settings.PARAMS_IN_SHIPMENT_SEND_BACK}{id}'
    })
    send_email_utility(subject, message, recipient_email)


def next_step_based_on_contract_category(current_user_role, contract_category):
    if contract_category == models.MASTER_CONTRACT:
        if current_user_role in [settings.SUPPLIER["name_value"], settings.SME["name_value"]]:
            return settings.CREDIT_CREATE_SHIPMENT
        else:
            return settings.CREDIT_PAYMENT_VIEW

    elif contract_category == models.NEW_CONTRACT:
        if current_user_role == settings.ADMIN["name_value"]:
            return settings.CREDIT_ADMIN_CREATE_CONTRACT
        else:
            return settings.REQUEST_NO_ACTION_NEEDED


def sme_reminder_mail(subject, recipient_name, recipient_email, id):
    """
    Function for sending reminder mail for sme

    :param recipient_name : user_name of recipient
    :param recipient_email: email id of recipient
    :parm  id : contract id
    :return:
    """
    message = render_to_string('transaction_app/reminder_mail.html', {
        'user_name': recipient_name,
        'login_link': f'{settings.FRONTEND_URL}{settings.SME_SIGN_URL}{id}',
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/'

    })
    send_email_utility(subject, message, recipient_email)


# def start():
#     """
#     Function for setting  periodical task for sending remainder mail
#     """
#     scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
#     scheduler.add_job(check_for_remainder, 'interval', minutes=15)
#
#     scheduler.start()


# def check_for_remainder():
#     """
#     Function for checking remainder time interval for sme
#     """
#     from transaction_app.models import ContractModel, SignedContractFilesModel, SME_SIGNED_CONTRACT, ADMIN_SIGNED_CONTRACT, \
#         SigningRemainderModel
#     from registration import models
#
#     remainder_interval = datetime.now()- timedelta(hours=24)
#     contract_obj = ContractModel.objects.filter(signed_contract_file__contract_doc_type=ADMIN_SIGNED_CONTRACT, \
#                                                 sme_remainder_contract__sending_time__lt =remainder_interval).exclude(
#                                                 signed_contract_file__contract_doc_type=SME_SIGNED_CONTRACT)
#
#     for contract in contract_obj:
#         if contract.is_master_contract:
#             sme_user = models.User.objects.get(master_contract = contract)
#         else:
#             sme_user = contract.fund_invoice.sme
#         remainder_obj = SigningRemainderModel.objects.get(contract = contract)
#         remainder_obj.count += 1
#         remainder_obj.sending_time = datetime.now()
#         remainder_obj.save()
#         sme_remainder_mail(settings.SIGN_CONTRACT_REMAINDER,sme_user.first_name,
#                            sme_user.email, contract.id )

def leads_next_step(user_object):
    """
    Function for generating next step in leads listing

    :param user_object: user
    :return: next action
    """
    from transaction_app.models import MasterContractStatusModel
    from contact_app.models import LeadsModel

    if user_object.user_role == settings.SME["number_value"]:
        if user_object.on_board_status in [ON_BOARD_USER_CREATED, ON_BOARD_PASSWORD_SET]:
            return settings.SME_ONBOARD
        elif user_object.on_board_status == ON_BOARD_IN_PROGRESS:
            leads_obj = LeadsModel.objects.get(sign_up_email=user_object.email)
            if leads_obj.sync_status in [settings.SYNC_COMPLETED, settings.NO_SYNC]:
                return settings.CREDIT_CHECK
            else:
                return settings.USER_NO_ACTION_NEEDED
        elif user_object.on_board_status == ON_BOARD_USER_REVIEWED:
            return settings.USER_ACTIVATION_PENDING
        elif user_object.on_board_status == ON_BOARD_COMPLETED:
            if user_object.master_contract is None:
                return settings.CREDIT_ADMIN_CREATE_MASTER_CONTRACT
            else:
                master_contract_status = MasterContractStatusModel.objects.filter(
                    contract=user_object.master_contract).first().action_taken
                if master_contract_status == settings.CREDIT_CONTRACT_ADMIN_CREATED:
                    return settings.CREDIT_CONTRACT_ADMIN_TO_SIGN
                else:
                    return settings.USER_NO_ACTION_NEEDED
        else:
            return settings.REQUEST_NO_ACTION_NEEDED
    elif user_object.user_role == settings.SUPPLIER["number_value"]:
        if user_object.on_board_status in [ON_BOARD_USER_CREATED, ON_BOARD_PASSWORD_SET]:
            return settings.SUPPLIER_ONBOARD
        elif user_object.on_board_status == ON_BOARD_IN_PROGRESS:
            return settings.USER_ACTIVATION_PENDING
        else:
            return settings.USER_NO_ACTION_NEEDED
    else:
        return settings.USER_NO_ACTION_NEEDED


def xero_token_generation(code):
    logger = logging.getLogger(__name__)
    # logger2 = logging.getLogger('')
    token_response = requests.post(url=settings.TOKEN_URL,
                                   headers={'Authorization': 'Basic ' + settings.BASIC_TOKEN},
                                   data={'grant_type': 'authorization_code', 'code': code,
                                         'redirect_uri': settings.REDIRECT_URI})
    logger.info("Response from xero token generation: ")
    logger.info(token_response)
    json_response = token_response.json()
    if 'error' in json_response:
        return False
    else:
        access_token = json_response['access_token']
        refresh_token = json_response['refresh_token']
        return [access_token, refresh_token]


def xero_tenant_id_generation(access_token):
    response_for_tenant = requests.get(
        url=settings.CONNECTION_URL,
        headers={
            'Authorization': 'Bearer ' + access_token, 'content-type': 'application/json'
        })
    tenant_response = response_for_tenant.json()
    if 'Status' in tenant_response:
        return False
    else:
        return tenant_response[0]['tenantId']


def xero_balance_sheet(access_token, tenant_id):
    last_year = date.today().year - 1
    last_year_start = date(last_year, 1, 1)
    last_year_end = date(last_year, 12, 31)

    response_balancesheet = requests.get(
        url=settings.BALANCE_SHEET_URL + f'fromDate= {last_year_start}&toDate={last_year_end}',
        headers={
            'Authorization': 'Bearer ' + access_token,
            'Xero-tenant-id': tenant_id,
            'Accept': 'application/json'
        }
    )
    return response_balancesheet.json()


def xero_profit_loss(access_token, tenant_id):
    last_year = date.today().year - 1
    last_year_start = date(last_year, 1, 1)
    last_year_end = date(last_year, 12, 31)

    response_profitloss = requests.get(
        url=settings.PROFIT_LOSS_URL + f'fromDate= {last_year_start}&toDate={last_year_end}',
        headers={
            'Authorization': 'Bearer ' + access_token,
            'Xero-tenant-id': tenant_id,
            'Accept': 'application/json',
        }
    )
    return response_profitloss.json()


def xero_bank_statement(access_token, tenant_id):
    response_bankstatement = requests.get(
        url=settings.BANK_STATEMENT_URL,
        headers={
            'Authorization': 'Bearer ' + access_token,
            'Xero-tenant-id': tenant_id,
            'Accept': 'application/json'
        }
    )
    return response_bankstatement.json()


def xero_organization_details(access_token, tenant_id):
    response_organization_info = requests.get(
        url=settings.ORGANIZATION_URL,
        headers={
            'Authorization': 'Bearer ' + access_token,
            'Xero-tenant-id': tenant_id,
            'Accept': 'application/json'
        }
    )
    return response_organization_info.json()


def refreshing_access_token(user_id):
    xero_user = XeroAuthTokenModel.objects.get(user=user_id)
    response = requests.post(url=settings.TOKEN_URL,
                             headers={'Authorization': 'Basic ' + settings.BASIC_TOKEN,
                                      'content--type': 'application/x-www-form-urlencoded'},
                             data={'grant_type': 'refresh_token', 'refresh_token': xero_user.refresh_token}
                             )
    token_response = response.json()
    return [token_response['access_token'], token_response['refresh_token']]


# def json_to_excel_format(json_response, user_object):
#     """
#     Function for generating excel file json response
#     :param json_response: json_response
#     :param user_object: user
#     """
#     if json_response['Status'] == "OK":
#         file_path = f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
#                     f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
#         if not os.path.exists(
#                 f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
#                 f'{settings.ON_BOARDING_DATA_FILE_PATH}/'):
#             os.makedirs(f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
#                         f'{settings.ON_BOARDING_DATA_FILE_PATH}/')

#         # Saving data to a json file
#         with open(f'{json_response["Reports"][0]["ReportType"]}.json', 'w') as f:
#             json.dump(json_response['Reports'], f)

#         df = pd.DataFrame()
#         writer = pd.ExcelWriter(file_path + f'{json_response["Reports"][0]["ReportType"]}.xlsx', engine='xlsxwriter')
#         df.to_excel(writer, sheet_name='Sheet1')

#         # Get the xlsxwriter workbook and worksheet objects.
#         workbook = writer.book
#         worksheet = writer.sheets['Sheet1']
#         # Add a header format.
#         header_format = workbook.add_format({
#             'bold': True,
#             'text_wrap': True,
#             'font_size': 11,
#             'valign': 'top',
#             'fg_color': '#eeeeee',
#             'border': 1})
#         # Add a section title format.
#         section_title_format = workbook.add_format({
#             'bold': True,
#             'text_wrap': True,
#             'font_size': 10,
#             'valign': 'bottom',
#             'fg_color': '#bcbcbc',
#             'border': 1})
#         # Add a row title format.
#         row_title_format = workbook.add_format({
#             'bold': True,
#             'text_wrap': True,
#             'font_size': 10,
#             'valign': 'bottom',
#             'fg_color': '#eeeeee',
#             'border': 1})
#         # Add a row format.
#         row_format = workbook.add_format({
#             'bold': True,
#             'text_wrap': True,
#             'font_size': 9,
#             'valign': 'bottom',
#             'fg_color': '#ffffff',
#             'border': 1})

#         # Header row
#         report_titles = json_response['Reports'][0]['ReportTitles']
#         if json_response['Reports'][0]['ReportTitles']:
#             worksheet.merge_range('A1:F1', json_response['Reports'][0]['ReportTitles'][1], header_format)
#             worksheet.merge_range('A2:F2', json_response['Reports'][0]['ReportTitles'][0], header_format)
#             worksheet.merge_range('A3:F3', json_response['Reports'][0]['ReportTitles'][2], header_format)

#         print(json_response['Reports'][0]['ReportTitles'][2])    
#         # worksheet.write(0, 0, report_titles[1], header_format)
#         # title = report_titles[0] + " " + report_titles[2]
#         # worksheet.write(1, 0, title, header_format)

#         row_data = json_response['Reports'][0]['Rows']
#         row_values = []

#         for num in range(0, len(row_data)):
#             column_values = []
#             if row_data[num]["RowType"] == "Header":
#                 column_values.append(row_title_format)
#                 for i in range(0, len(row_data[num]["Cells"])):
#                     column_values.append(row_data[num]["Cells"][i]["Value"])
#                 row_values.append(column_values)
#             elif row_data[num]["RowType"] in ["Section", "Row"]:
#                 if row_data[num]["RowType"] == "Section":
#                     column_values.append(section_title_format)
#                 else:
#                     column_values.append(row_title_format)
#                 column_values.append(row_data[num]["Title"])
#                 row_values.append(column_values)
#                 for row in range(len(row_data[num]["Rows"])):
#                     column_values = [row_format]
#                     for col in range(0, len(row_data[num]["Rows"][row]["Cells"])):
#                         column_values.append(row_data[num]["Rows"][row]["Cells"][col]["Value"])
#                     row_values.append(column_values)

#         for row_num in range(len(row_values)):
#             for index in range(1, len(row_values[row_num])):
#                 worksheet.write(row_num + 2, index - 1, row_values[row_num][index], row_values[row_num][0])
#         worksheet.set_column(0, 0, 45)
#         writer.save()
#     else:
#         print(f"Getting a {str(json_response['Status'])} on get connection request")


def json_to_excel_response(json_response, user_object):
    """
    Function for generating excel file json resopose
    :param json_respose: json_respose
    :param user_object: user
    """
    file_path = f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
                f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
    if not os.path.exists(
            f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
            f'{settings.ON_BOARDING_DATA_FILE_PATH}/'):
        os.makedirs(f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
                    f'{settings.ON_BOARDING_DATA_FILE_PATH}/')

        # Saving data to a json file
        with open(f'{json_response["Reports"][0]["ReportType"]}.json', 'w') as f:
            json.dump(json_response['Reports'], f)

    df = pd.DataFrame()
    writer = pd.ExcelWriter(file_path + f'{json_response["Reports"][0]["ReportType"]}.xlsx', engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1')

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    # Add a header format.
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 11,
        'valign': 'vcenter',
        'fg_color': '#eeeeee',
        'align': 'center',
        'border': 1})
    # Add a section title format.
    section_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 10,
        'valign': 'bottom',
        'fg_color': '#bcbcbc',
        'border': 1})
    # Add a row title format.
    row_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 10,
        'valign': 'bottom',
        'fg_color': '#eeeeee',
        'border': 1})
    # Add a row format.
    row_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 9,
        'valign': 'bottom',
        'fg_color': '#ffffff',
        'border': 1})

    # Header row
    report_titles = json_response['Reports'][0]['ReportTitles']

    worksheet.merge_range('A1:B1', json_response['Reports'][0]['ReportTitles'][1], header_format)
    worksheet.merge_range('A2:B2', json_response['Reports'][0]['ReportTitles'][0], header_format)
    worksheet.merge_range('A3:B3', json_response['Reports'][0]['ReportTitles'][2], header_format)

    row_data = json_response['Reports'][0]['Rows']
    space = ""
    for num in range(0, len(row_data)):
        if row_data[num]["RowType"] == "Header":
            row_num = len(json_response['Reports'][0]['ReportTitles'])

        elif row_data[num]["RowType"] == "Section":
            if row_data[num]["Title"] is not space:
                worksheet.merge_range(f'A{row_num + 1}:B{row_num + 1}', row_data[num]["Title"], section_title_format)
                # worksheet.write(row_num, 0, row_data[num]["Title"], section_title_format)

                row_num += 1
            for l in range(len(row_data[num]["Rows"])):
                if row_data[num]["Rows"][l]["RowType"] == "SummaryRow":
                    raw_list = row_data[num]["Rows"][l]
                    for i in range(0, len(raw_list)):
                        worksheet.write(row_num, i, raw_list["Cells"][i]["Value"], row_format)
                        row_num += 1

                if row_data[num]["Rows"][l]["RowType"] == "Row":
                    raw_list = row_data[num]["Rows"][l]
                    for i in range(1, len(raw_list)):
                        worksheet.write(row_num, i, raw_list["Cells"][i]["Value"], row_format)
                        row_num += 1
    worksheet.set_column(0, 0, 45)

    workbook.close()
    # pdfkit.from_string(file_path + f'{json_response["Reports"][0]["ReportType"]}.xlsx', file_path', )


def profit_loss_response(json_response, user_object):
    """
    Function for generating excel file json resopose
    :param json_respose: json_respose
    :param user_object: user
    """
    file_path = f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
                f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
    if not os.path.exists(
            f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
            f'{settings.ON_BOARDING_DATA_FILE_PATH}/'):
        os.makedirs(f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
                    f'{settings.ON_BOARDING_DATA_FILE_PATH}/')

        # Saving data to a json file
        with open(f'{json_response["Reports"][0]["ReportType"]}.json', 'w') as f:
            json.dump(json_response['Reports'], f)

    df = pd.DataFrame()
    writer = pd.ExcelWriter(file_path + f'{json_response["Reports"][0]["ReportType"]}.xlsx', engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1')

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    # Add a header format.
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 14,
        'valign': 'vcenter',
        'fg_color': '#eeeeee',
        'align': 'left',
        'border': 1})
    # Add a section title format.
    section_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 11,
        'valign': 'bottom',
        'fg_color': '#bcbcbc',
        'border': 1})
    # Add a row title format.
    row_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 10,
        'valign': 'bottom',
        'fg_color': '#eeeeee',
        'border': 1})
    # Add a row format.
    row_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 9,
        'valign': 'bottom',
        'fg_color': '#ffffff',
        'border': 1})

    # Header row
    report_titles = json_response['Reports'][0]['ReportTitles']

    worksheet.merge_range('A1:M1', json_response['Reports'][0]['ReportTitles'][1], header_format)
    worksheet.merge_range('A2:M2', json_response['Reports'][0]['ReportTitles'][0], header_format)
    worksheet.merge_range('A3:M3', json_response['Reports'][0]['ReportTitles'][2], header_format)

    row_data = json_response['Reports'][0]['Rows']
    space = ""
    organizational_asset = 0
    for num in range(0, len(row_data)):
        header_data = json_response['Reports'][0]['Rows'][num]
        if row_data[num]["RowType"] == "Header":
            row_num = len(json_response['Reports'][0]['ReportTitles']) + 1
            row_num += 1
        if row_data[0]['RowType'] == 'Header':
            header_data = json_response['Reports'][0]['Rows'][0]
            for j in range(len(json_response['Reports'][0]['Rows'][0]["Cells"])):
                if space == header_data["Cells"][j]["Value"]:
                    worksheet.write(4, j, "Account", row_format)
                else:
                    worksheet.write(4, j, header_data["Cells"][j]["Value"], row_format)
            worksheet.write(4, len(json_response['Reports'][0]['Rows'][0]["Cells"]), "Total", row_format)
        if row_data[num]['RowType'] == 'Section':
            if space != row_data[num]["Title"]:
                worksheet.merge_range(f'A{row_num + 1}:N{row_num + 1}', row_data[num]["Title"], section_title_format)
            for i in range(len(row_data[num]['Rows'])):
                if len(row_data[num]['Rows']) > i:
                    if row_data[num]['Rows'][i]["RowType"] == 'Row':
                        row_num += 1
                        total_value = 0
                        for j in range(13):
                            if j > 0:
                                total_value += float(row_data[num]['Rows'][i]["Cells"][j]["Value"])
                            if row_data[num]['Rows'][i]["Cells"][0]["Value"] == "Sales":
                                organizational_asset = total_value
                            worksheet.write(row_num, j, row_data[num]['Rows'][i]["Cells"][j]["Value"], row_format)
                        worksheet.write(row_num, 13, total_value, row_format)
                if len(row_data[num]['Rows']) > i:
                    if row_data[num]['Rows'][i]["RowType"] == 'SummaryRow':
                        row_num += 1
                        total_value = 0
                        for j in range(13):
                            if j > 0:
                                total_value += float(row_data[num]['Rows'][i]["Cells"][j]["Value"])
                            if row_data[num]['Rows'][i]["Cells"][0]["Value"] == "Total Current Liabilities":
                                organizational_asset = total_value
                            worksheet.write(row_num, j, row_data[num]['Rows'][i]["Cells"][j]["Value"], row_format)
                        worksheet.write(row_num, 13, total_value, row_format)
    worksheet.set_column(0, 0, 45)
    for i in range(1, 13):
        worksheet.set_column(i, i, 10)

    workbook.close()
    return organizational_asset


def send_otp_for_login_or_set_password(user_object, otp):
    from botocore.exceptions import ClientError
    if settings.PRODUCTION is True:
        logger = logging.getLogger(__name__)
        logger.info("user :")
        sns_client = boto3.client(
            'sns',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.REGION_NAME
        )
        username = user_object.first_name if user_object.first_name else 'User'
        mobile_num = user_object.phone_number if user_object.phone_number else '+919074004982'
        message = f' Dear {username.title()}, {otp} is your OTP for login. do not share with anyone. OCEAN'
        response = None
        try:
            response = sns_client.publish(
                PhoneNumber=str(mobile_num),
                Message=message
            )
            response = sns_client.publish(TopicArn=settings.AWS_TOPIC_ARN, Message=message, Subject='OTP_VALIDATION',
                                          MessageAttributes={'TransactionType': {'DataType': 'String',
                                                                                 'StringValue': 'OTP_VALIDATION'}})
        except ClientError:
            logger.exception("The security token included in the request is invalid")
        if response is not None:
            return response['ResponseMetadata']['HTTPStatusCode']


def get_organization_details(json_Response):
    """
        Function for getting organization details exttrations from Xero response
        :param json_Response : xero orgaization json response
        :return: orgaization details for onboarding
    """
    output_dict = dict()
    output_dict["country_name"] = ''
    output_dict["Registered_Address"] = ''
    if json_Response.get('addresses'):
        output_dict["country_name"] = json_Response['addresses'][0].get("country")
        address_list = []
        if json_Response['addresses'][0].get("line1"):
            address_list.append(json_Response['addresses'][0].get("line1"))
        if json_Response['addresses'][0].get("line2"):
            address_list.append(json_Response['addresses'][0].get("line2"))
        if json_Response['addresses'][0].get("city"):
            address_list.append(json_Response['addresses'][0].get("city"))
        if json_Response['addresses'][0].get("region"):
            address_list.append(json_Response['addresses'][0].get("region"))
        if json_Response['addresses'][0].get("country"):
            address_list.append(json_Response['addresses'][0].get("country"))
        if json_Response['addresses'][0].get("postalCode"):
            address_list.append(json_Response['addresses'][0].get("postalCode"))
        output_dict["Registered_Address"] = ','.join(address_list)
    output_dict["RegistrationNumber"] = json_Response.get("registrationNumber")
    output_dict["Organization_name"] = json_Response.get('companyName')

    output_dict["Physical_Address"] = ''
    if len(json_Response['addresses']) > 1:
        address_list2 = []
        if json_Response['addresses'][0].get("line1"):
            address_list2.append(json_Response['addresses'][1].get("line1"))
        if json_Response['addresses'][0].get("line2"):
            address_list2.append(json_Response['addresses'][1].get("line2"))
        if json_Response['addresses'][0].get("city"):
            address_list2.append(json_Response['addresses'][1].get("city"))
        if json_Response['addresses'][0].get("region"):
            address_list2.append(json_Response['addresses'][1].get("region"))
        if json_Response['addresses'][0].get("country"):
            address_list2.append(json_Response['addresses'][1].get("country"))
        if json_Response['addresses'][0].get("postalCode"):
            address_list2.append(json_Response['addresses'][1].get("postalCode"))
        output_dict["Physical_Address"] = ','.join(address_list2)
    # Address = ""
    # for key in settings.ADDRESS_FIELD_KEY:
    #     if key in json_Response["Organisations"][0]["Addresses"][1]:
    #         Address += json_Response["Organisations"][0]["Addresses"][1][key]
    #     Address += ","
    # output_dict["Physical_Address"] = Address
    output_dict["Website"] = ''
    if json_Response["webLinks"]:
        output_dict["Website"] = json_Response["webLinks"][0].get('url')
    output_dict["Phone_number"] = ''
    if json_Response["phoneNumbers"]:
        output_dict["Phone_number"] = json_Response["phoneNumbers"][0].get("number")

    # for key in settings.ADDITIONAL_INFO_KEY:
    #     if key in json_Response["Organisations"][0]:
    #         if key == "TaxNumber" and json_Response["Organisations"][0]["CountryCode"] == "GB":
    #             output_dict["Additional Info"] = {"VATNumber": json_Response["Organisations"][0][key]}
    #         elif key == "EmployerIdentificationNumber":
    #             output_dict["Additional Info"] = {key: json_Response["Organisations"][0][key]}
    #         else:
    #             pass
    return output_dict


def payment_acknowledgment_mail(subject, recipient_name, sender_name, recipient_email, paying_amount,
                                reference_number):
    """
        Function for sending payment acknowledgment mail to supplier

        :param recipient_name : user_name of recipient
        :param sender_name : sender_name
        :param recipient_email: email id of recipient
        :param paying_amount : paying_amount
        :param reference_number : reference_number of payment
        :return:
    """
    message = render_to_string('transaction_app/payment_acknowledgment_supplier.html', {
        'user_name': recipient_name,
        'sender_name': sender_name,
        'paying_amount': paying_amount,
        'reference_number': reference_number,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/'

    })
    send_email_utility(subject, message, recipient_email)


def payment_acknowledgment_mail_sme(subject, recipient_name, sender_name, supplier_name, recipient_email):
    """
        Function for sending payment acknowledgment mail to sme

        :param recipient_name : user_name of recipient
        :param sender_name : sender_name
        :param recipient_email: email id of recipient
        :param of supplier_name: supplier name
        :return:
    """
    message = render_to_string('transaction_app/payment_acknowledgment_sme.html', {
        'user_name': recipient_name,
        'sender_name': sender_name,
        'supplier_name': supplier_name,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/'

    })
    send_email_utility(subject, message, recipient_email)


def get_new_contract_number(contract_object):
    """
        Function for getting new contract number
        :param : object of contract model
        :return : contract number
    """
    today = date.today()
    current_year = u'%4s' % today.year
    if contract_object is not None:
        contract_no = int(contract_object.contract_number[7:])
        year = contract_object.contract_number[2:6]
        if current_year > year:
            contract_no = 0
    else:
        contract_no = 0
    contract_no += 1
    contract_no = str(contract_no).zfill(4)
    return "0-" + str(current_year) + "/" + str(contract_no)
    # 0-2022/0001


def calculate_total_cogs_value(user_id):
    """
        Function for calculating total cogs amount in sme page
        :param : id of corresponding sme
        :return : 
    """
    from transaction_app.models import FundInvoiceModel
    total_invoice_amount = FundInvoiceModel.objects.filter(
        is_deleted=False,
        sme_id=user_id). \
        aggregate(Sum('invoice_total_amount'))
    return total_invoice_amount


def calculate_total_cogs_amount_for_admin():
    """
        Function for calculating total cogs amount in admin page
        :param :
        :return : total cogs amount
    """
    from transaction_app.models import FundInvoiceModel
    total_invoice_amount = FundInvoiceModel.objects.filter(
        is_deleted=False). \
        aggregate(Sum('invoice_total_amount'))
    return total_invoice_amount


def calculate_total_sales_amount_for_admin():
    """
        Function for calculating total sales amount in admin page
        :param :
        :return : total sales amount
    """
    from transaction_app.models import FundInvoiceModel, ContractModel

    total_sales_value = (FundInvoiceModel.objects.filter(
        is_deleted=False). \
                         aggregate(Sum('total_sales_amount')).get(
        'total_sales_amount__sum') or 0) + (ContractModel.objects.all(). \
                                            aggregate(Sum('total_sales_amount')).get('total_sales_amount__sum') or 0)
    return total_sales_value


def calculate_overdue_amount(user_object):
    """
        Function for calculating overdue amount for an sme
        :param user_object : user object
        :return : overdue amount
    """
    from transaction_app.models import SmeTermsAmountModel, SmeTermsInstallmentModel, FundInvoiceModel, PaymentModel, \
        PAYMENT_TO_FACTORING_COMPANY_BY_SME, SignedContractFilesModel, TERMS_CRITERIA_DAYS_FROM_LAST_PAYMENT, \
        INSTALLMENT_PERIOD_WEEKLY
    fund_invoice = FundInvoiceModel.objects.filter(sme=user_object)
    current_date = datetime.now()
    for fund_invoice_obj in fund_invoice:
        due_amount = 0
        if fund_invoice_obj.contract_category == settings.MASTER_CONTRACT["number_value"]:
            if user_object.master_contract is not None:
                sme_amount_payment_term = SmeTermsAmountModel.objects.filter(payment_term=
                                                                             user_object.master_contract.contract_type.
                                                                             payment_terms).order_by("id")
                sme_installment_amount = SmeTermsInstallmentModel.objects.filter(payment_term=
                                                                                 user_object.master_contract.
                                                                                 contract_type.payment_terms)
                approval_date = fund_invoice_obj.date_approved
                if sme_amount_payment_term.exists():
                    for sme_amount_term_obj in sme_amount_payment_term:
                        if sme_amount_term_obj.criteria == TERMS_CRITERIA_DAYS_FROM_LAST_PAYMENT:
                            payment_obj = PaymentModel.objects.filter(fund_invoice=fund_invoice_obj,
                                                                      payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                                      term_order=sme_amount_term_obj.terms_order - 1)
                            if payment_obj.exists():
                                due_date = approval_date + payment_obj.first().date_modified
                        else:
                            due_date = approval_date + timedelta(days=sme_amount_term_obj.days)
                        if datetime.date(current_date) > due_date:
                            payment_obj = PaymentModel.objects.filter(fund_invoice=fund_invoice_obj,
                                                                      payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                                      term_order=sme_amount_term_obj.terms_order)
                            if not payment_obj.exists():
                                due_amount += sme_amount_term_obj.values
                else:
                    for unit in (1, sme_installment_amount.first().units + 1):
                        if sme_installment_amount.first().period == INSTALLMENT_PERIOD_WEEKLY:
                            due_date = approval_date + timedelta(days=7)
                        else:
                            due_date = approval_date + timedelta(days=30)
                        if datetime.date(current_date) > due_date:
                            payment_obj = PaymentModel.objects.filter(fund_invoice=fund_invoice_obj,
                                                                      payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                                      term_order=unit)
                            if not payment_obj.exists():
                                due_amount += (fund_invoice_obj.total_sales_amount / 3) * (
                                        sme_installment_amount.first().units - (unit - 1))

        elif fund_invoice_obj.contract_category == settings.NEW_CONTRACT["number_value"]:
            if fund_invoice_obj.fund_invoice_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists():
                sme_amount_payment_term = SmeTermsAmountModel.objects.filter(payment_term=
                                                                             fund_invoice_obj.contract_fund_invoice.
                                                                             all().first().contract_type.payment_terms). \
                    order_by("id")
                sme_installment_amount = SmeTermsInstallmentModel.objects.filter(
                    payment_term=fund_invoice_obj.contract_fund_invoice.all().first().contract_type.payment_terms)
                approval_date = SignedContractFilesModel.objects.filter(contract=fund_invoice_obj.
                                                                        contract_fund_invoice.first()).first(). \
                    date_modified
                if sme_amount_payment_term.exists():
                    for sme_amount_term_obj in sme_amount_payment_term:
                        if sme_amount_term_obj.criteria == TERMS_CRITERIA_DAYS_FROM_LAST_PAYMENT:
                            payment_obj = PaymentModel.objects.filter(fund_invoice=fund_invoice_obj,
                                                                      payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                                      term_order=sme_amount_term_obj.terms_order - 1)
                            if payment_obj.exists():
                                due_date = approval_date + payment_obj.first().date_modified
                        else:
                            due_date = approval_date + timedelta(days=sme_amount_term_obj.days)
                            if datetime.date(current_date) > due_date:
                                payment_obj = PaymentModel.objects.filter(fund_invoice=fund_invoice_obj,
                                                                          payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                                          term_order=sme_amount_term_obj.terms_order)
                                if not payment_obj.exists():
                                    due_amount += sme_amount_term_obj.values
                else:
                    for unit in (1, sme_installment_amount.first().units + 1):
                        if sme_installment_amount.first().period == INSTALLMENT_PERIOD_WEEKLY:
                            due_date = approval_date + timedelta(days=7)
                        else:
                            due_date = approval_date + timedelta(days=30)
                        if datetime.date(current_date) > due_date:
                            payment_obj = PaymentModel.objects.filter(fund_invoice=fund_invoice_obj,
                                                                      payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                                      term_order=unit)
                            if not payment_obj.exists():
                                due_amount += (fund_invoice_obj.contract_fund_invoice.all().first().total_sales_amount
                                               / 3) * (sme_installment_amount.first().units - (unit - 1))

        else:
            pass
        return round(due_amount, 2)


def codat_company_creation(company_name):
    """
    Function for create company in codat
    """
    response = requests.post("https://api.codat.io/companies",
                             data="{'name': '" + company_name + "'}",
                             headers={"Content-Type": "application/json",
                                      "Accept": "application/json",
                                      "Authorization": settings.CODAT_AUTHORIZATION_KEY})
    response_data = response.json()
    return response_data


def codat_get_company_by_id(company_id):
    """
    Function for create company in codat
    """
    response = requests.get(f"https://api.codat.io/companies/{company_id}",
                            headers={"Content-Type": "application/json",
                                     "Accept": "application/json",
                                     "Authorization": settings.CODAT_AUTHORIZATION_KEY})
    response_data = response.json()
    return response_data


def get_codat_xero_balance_sheet_data(company_id, user_object):
    """
    Function for get deta from codat xero
    """
    balance_sheet_response = requests.get(
        f"https://api.codat.io/companies/{company_id}/data/financials/balanceSheet?periodLength=1&periodsToCompare=11",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "Authorization": settings.CODAT_AUTHORIZATION_KEY})
    comapny_obj = get_codat_xero_company_info(company_id)
    info = {'type': 'BalanceSheet',
            'title': comapny_obj.get('companyName'),
            'sub_title': 'Balance Sheet'}
    return codat_profit_loss_response(balance_sheet_response.json(), user_object, info)


def get_codat_xero_profit_and_loss_data(company_id, user_object):
    profit_loss_response = requests.get(
        f"https://api.codat.io/companies/{company_id}/data/financials/profitAndLoss?periodLength=1&periodsToCompare=11",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "Authorization": settings.CODAT_AUTHORIZATION_KEY})
    comapny_obj = get_codat_xero_company_info(company_id)
    info = {'type': 'ProfitAndLoss',
            'title': comapny_obj.get('companyName'),
            'sub_title': 'Profit and Loss'}
    return codat_profit_loss_response(profit_loss_response.json(), user_object, info)


def get_codat_xero_company_info(company_id):
    company_info_response = requests.get(
        f"https://api.codat.io/companies/{company_id}/data/info",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "Authorization": settings.CODAT_AUTHORIZATION_KEY})
    return company_info_response.json()


def codat_data(account, data):
    for items in data:
        if items.get('items'):
            codat_data(account, items['items'])
        else:
            account[items['name']] = items['value']

    return account


def codat_profit_loss_response(json_response, user_object, info):
    """
    Function for generating excel file json resopose
    :param json_respose: json_respose
    :param user_object: user
    """
    if not json_response or not json_response.get('reports'):
        return 0

    file_path = f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
                f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
    if not os.path.exists(
            f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
            f'{settings.ON_BOARDING_DATA_FILE_PATH}/'):
        os.makedirs(f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
                    f'{settings.ON_BOARDING_DATA_FILE_PATH}/')

        # Saving data to a json file
        with open(file_path + f"{info['type']}.json", 'w') as f:
            json.dump(json_response['reports'], f)

    df = pd.DataFrame()
    writer = pd.ExcelWriter(file_path + f"{info['type']}.xlsx", engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1')

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    # Add a header format.
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 14,
        'valign': 'vcenter',
        'fg_color': '#eeeeee',
        'align': 'left',
        'border': 1})
    # Add a section title format.
    section_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 11,
        'valign': 'bottom',
        'fg_color': '#bcbcbc',
        'border': 1})
    # Add a row title format.
    row_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 10,
        'valign': 'bottom',
        'fg_color': '#eeeeee',
        'border': 1})
    # Add a row format.
    row_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 9,
        'valign': 'bottom',
        'fg_color': '#ffffff',
        'border': 1})
    accouts_objects = {'heads': [], 'items': []}
    for accounts in json_response['reports']:

        for main_type in accounts:
            if main_type not in ['date', 'netAssets', 'fromDate', 'toDate', 'netProfit', 'grossProfit',
                                 'netOperatingProfit', 'netOtherIncome']:
                for key, value in codat_data({}, accounts[main_type]['items']).items():
                    if accounts[main_type]['name'] not in accouts_objects:
                        accouts_objects['items'].append(accounts[main_type]['name'])
                        accouts_objects[accounts[main_type]['name']] = {'items': []}
                    if key not in accouts_objects[accounts[main_type]['name']]:
                        accouts_objects[accounts[main_type]['name']]['items'].append(key)
                        accouts_objects[accounts[main_type]['name']][key] = {}
                    if accounts.get('date', accounts.get('toDate')) not in accouts_objects['heads']:
                        accouts_objects['heads'].append(accounts.get('date', accounts.get('toDate')))
                    accouts_objects[accounts[main_type]['name']][key][
                        accounts.get('date', accounts.get('toDate'))] = value
    worksheet.merge_range(0, 0, 0, len(accouts_objects['heads']) + 1, info['title'], header_format)
    worksheet.merge_range(1, 0, 1, len(accouts_objects['heads']) + 1, info['sub_title'], header_format)
    worksheet.merge_range(2, 0, 2, len(accouts_objects['heads']) + 1, 'As at ' + datetime.strptime(
        json_response['mostRecentAvailableMonth'], '%Y-%m-%dT%H:%M:%S').strftime('%d %B %Y'), header_format)

    row, column = 4, 0
    organizational_asset = 0
    worksheet.write(row, column, "Account", row_format)
    for heading in accouts_objects['heads']:
        column += 1
        worksheet.write(row, column, datetime.strptime(heading, '%Y-%m-%dT%H:%M:%S').strftime('%d %b %Y'), row_format)
    column += 1
    worksheet.write(row, column, "Total", row_format)
    accouts_objects['items'].sort()
    for titles in accouts_objects['items']:
        row += 1
        column = 0
        worksheet.merge_range(row, column, row, len(accouts_objects['heads']) + 1, titles, section_title_format)
        accouts_objects[titles]['items'].sort()
        for datas in accouts_objects[titles]['items']:
            row += 1
            column = 0
            worksheet.write(row, column, datas, row_format)
            total = 0
            for heading in accouts_objects['heads']:
                column += 1
                worksheet.write(row, column, str(accouts_objects[titles][datas].get(heading, '0.00')), row_format)
                total += accouts_objects[titles][datas].get(heading, 0.0)
            if datas in ['Sales']:
                organizational_asset = total
            elif titles in ['Liabilities', 'Income']:
                organizational_asset += total
            column += 1
            worksheet.write(row, column, total, row_format)

    worksheet.set_column(0, 0, 45)
    worksheet.set_column(1, len(accouts_objects['heads']) + 1, 10)
    workbook.close()
    return organizational_asset


from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import register_events
from contact_app.models import LeadsModel
from registration.models import User


def start():
    """
    Function for scheduling codat data sync complete check
    """
    scheduler = BackgroundScheduler()
    register_events(scheduler)

    @scheduler.scheduled_job('interval', minutes=4, name='sync_check')
    def sync_check():
        leads_obj = LeadsModel.objects.filter(sync_status=settings.SYNC_STARTED)
        for leads in leads_obj:
            codat_response(leads)

    scheduler.start()


def codat_response(lead_object=None, user_object=None, request=None, is_from_scheduler=True):
    """
    Function for saving codat data
    :param lead_object: lead object
    :param user_object: user object
    :param request : request
    :param is_from_scheduler : boolean value
    """
    from registration.serializers import UserDetailSerializers
    from transaction_app.serializers import NotificationModelSerializer
    from transaction_app.models import NotificationModel
    if lead_object is None:
        lead_object = LeadsModel.objects.get(sign_up_email=user_object.email)
    company_info_response = requests.get(
        f"https://api.codat.io/companies/{lead_object.company_id}/dataStatus",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "Authorization": settings.CODAT_AUTHORIZATION_KEY})

    company_response = codat_get_company_by_id(lead_object.company_id)
    sync_state = settings.NO_SYNC
    leads_company_info = {}
    input_dict = dict()
    if user_object is None:
        user_object = User.objects.get(email=lead_object.sign_up_email)
    if not company_response.get('dataConnections'):
        if user_object.on_boarding_details is not None:
            lead_object.sync_status = settings.SYNC_COMPLETED
            lead_object.save()
            return sync_state
        else:
            return sync_state
    elif company_response.get('dataConnections')[0].get('dataConnectionErrors'):
        return sync_state

    elif company_info_response.json()["profitAndLoss"]["currentStatus"] == "Complete" \
            and company_info_response.json()["balanceSheet"]["currentStatus"] == "Complete" and \
            company_info_response.json()["company"]["currentStatus"] == "Complete":
        sync_state = settings.SYNC_COMPLETED
        lead_object.sync_status = settings.SYNC_COMPLETED
        lead_object.save()
    else:
        sync_state = settings.SYNC_DELAY

    file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
                f'{settings.ON_BOARDING_DATA_FILE_PATH}/'

    if user_object.on_boarding_details is not None:
        user_detail_object = user_object.on_boarding_details
    else:
        # Adding xero files to userdetail object
        serializer_data = dict()
        serializer_data["user_detail_path"] = file_path
        user_detail_serializer = UserDetailSerializers(data=serializer_data, context={"request": request})
        user_detail_serializer.is_valid(raise_exception=True)
        user_detail_object = user_detail_serializer.save()
        user_object.on_boarding_details = user_detail_object

    if company_info_response.json()["company"]["currentStatus"] == "Complete":
        company_info = get_organization_details(get_codat_xero_company_info(lead_object.company_id))
        input_dict["company_name"] = company_info["Organization_name"]
        input_dict["company_registration_id"] = company_info["RegistrationNumber"]
        input_dict["company_physical_address"] = company_info["Physical_Address"]
        input_dict["company_registered_address"] = company_info["Registered_Address"]
        input_dict["company_website"] = company_info["Website"]
        input_dict["company_telephone_number"] = company_info["Phone_number"]
        # if company_info.get('country_name') and lead_object.company_registered_in != company_info.get('country_name'):
        #     lead_object.company_registered_in = company_info.get('country_name')
        #     lead_object.save()
        if company_info['Organization_name']:
            leads_company_info['company_name'] = company_info['Organization_name']
        if company_info['RegistrationNumber']:
            leads_company_info['company_registration_id'] = company_info['RegistrationNumber']
        if company_info['Physical_Address']:
            leads_company_info['company_physical_address'] = company_info['Physical_Address']
        if company_info['Registered_Address']:
            leads_company_info['company_registered_address'] = company_info['Registered_Address']
        if company_info['Website']:
            leads_company_info['company_website'] = company_info['Website']
        if company_info['Phone_number']:
            leads_company_info['company_telephone_number'] = company_info['Phone_number']
    if company_info_response.json()["profitAndLoss"]["currentStatus"] == "Complete":
        annual_revenue = get_codat_xero_profit_and_loss_data(lead_object.company_id, user_object)
        input_dict["last_fy_annual_revenue"] = annual_revenue
        if os.path.exists(settings.MEDIA_ROOT + '/' + file_path + "ProfitAndLoss.xlsx"):
            input_dict["last_year_profit_loss"] = file_path + "ProfitAndLoss.xlsx"

    if company_info_response.json()["balanceSheet"]["currentStatus"] == "Complete":
        debt_amount = get_codat_xero_balance_sheet_data(lead_object.company_id, user_object)
        input_dict["total_debt_amounts"] = debt_amount
        if os.path.exists(settings.MEDIA_ROOT + '/' + file_path + "BalanceSheet.xlsx"):
            input_dict["current_balance_sheet"] = file_path + "BalanceSheet.xlsx"

    if sync_state == settings.SYNC_COMPLETED:
        codat_bank_statement_response(lead_object.company_id, user_object)
        if os.path.exists(settings.MEDIA_ROOT + '/' + file_path + "BankSummary.xlsx"):
            input_dict["last_year_account_statement"] = file_path + "BankSummary.xlsx"
        if os.path.exists(settings.MEDIA_ROOT + '/' + file_path):
            threading_process = threading.Thread(target=generate_sme_zip_file,
                                                 args=(user_object.email,))
            threading_process.start()

    user_detail_object.__dict__.update(input_dict)
    user_detail_object.save()
    user_dict = {}
    user_dict["on_boarding_details"] = user_detail_object
    user_object.__dict__update = user_dict
    user_object.save()
    lead_object.__dict__.update(leads_company_info)
    lead_object.save()

    if is_from_scheduler and sync_state == settings.SYNC_COMPLETED:

        notification_obj = NotificationModel.objects.filter(on_boarding_details=user_detail_object.id,
                                                            user=user_object.id, type=settings.USER_DETAILS_ADDED)

        if not notification_obj.exists():
            codat_sync_completed_mail(id=user_object.on_boarding_details_id, sme_name=user_object.first_name,
                                      user_id=user_object.id)
            notification_data = {"on_boarding_details": user_detail_object.id,
                                 "user": user_object.id,
                                 "notification": "User Detail was Added",
                                 "type": settings.USER_DETAILS_ADDED,
                                 "description": "User Activation is Pending"}
            notification_serializer = NotificationModelSerializer(data=notification_data)
            if notification_serializer.is_valid(raise_exception=True):
                notification_serializer.save()
    return sync_state
    # if company_info_response.json()["profitAndLoss"]["currentStatus"]== "Complete"  \
    #     and company_info_response.json()["balanceSheet"]["currentStatus"] == "Complete" :
    #
    #     is_sync_complated = True
    #     if user_object is None:
    #         user_object = User.objects.get(email=lead_object.sign_up_email)
    #     debt_amount = get_codat_xero_balance_sheet_data(lead_object.company_id, user_object)
    #     annual_revenue = get_codat_xero_profit_and_loss_data(lead_object.company_id, user_object)
    #     codat_bank_statement_response(lead_object.company_id, user_object)
    #     company_info = get_organization_details (get_codat_xero_company_info(lead_object.company_id))
    #     file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
    #                 f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
    #
    #     if user_object.on_boarding_details is not None:
    #         user_detail_object =  user_object.on_boarding_details
    #     else:
    #         # Adding xero files to userdetail object
    #         serializer_data = dict()
    #         serializer_data["user_detail_path"] = file_path
    #         user_detail_serializer = UserDetailSerializers(data=serializer_data, context={"request": request})
    #         user_detail_serializer.is_valid(raise_exception=True)
    #         user_detail_object = user_detail_serializer.save()
    #         user_detail_object.last_fy_annual_revenue = annual_revenue
    #         user_detail_object.total_debt_amounts = debt_amount
    #
    #         user_object.on_boarding_details = user_detail_object
    #         user_object.save()
    #
    #     user_detail_object.current_balance_sheet = file_path + "BalanceSheet.xlsx"
    #     user_detail_object.last_year_account_statement = file_path + "BankSummary.xlsx"
    #     user_detail_object.last_year_profit_loss = file_path + "ProfitAndLoss.xlsx"
    #     user_detail_object.company_name = company_info["Organization_name"]
    #     user_detail_object.company_registration_id = company_info["RegistrationNumber"]
    #     user_detail_object.company_physical_address = company_info["Physical_Address"]
    #     user_detail_object.company_registered_address = company_info["Registered_Address"]
    #     user_detail_object.company_website = company_info["Website"]
    #     user_detail_object.company_telephone_number = company_info["Phone_number"]
    #     user_detail_object.save()
    #     lead_object.sync_status=settings.SYNC_COMPLETED
    #     lead_object.save()
    #
    #     if is_from_scheduler:
    #         codat_sync_completed_mail(lead_object.company_name)
    #         notification_data = {"on_boarding_details": user_detail_object.id,
    #                              "user": user_object.id,
    #                              "notification": "User Detail was Added",
    #                              "type": settings.USER_DETAILS_ADDED,
    #                              "description": "User Activation is Pending"}
    #         notification_serializer = NotificationModelSerializer(data=notification_data)
    #
    #         if notification_serializer.is_valid(raise_exception=True):
    #             notification_serializer.save()
    #     return is_sync_complated
    # else:
    #     return is_sync_complated


def codat_bank_statement_response(company_id, user_object):
    company_response = codat_get_company_by_id(company_id)
    connectionId = ''
    for connection_obj in company_response.get('dataConnections'):
        if connection_obj.get('sourceType') == 'Accounting':
            connectionId = connection_obj['id']
    bank_statement_response = requests.get(
        f"https://api.codat.io/companies/{company_id}/connections/{connectionId}/data/bankAccounts",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "Authorization": settings.CODAT_AUTHORIZATION_KEY})
    comapny_obj = get_codat_xero_company_info(company_id)
    info = {'type': 'BankSummary',
            'title': comapny_obj.get('companyName'),
            'sub_title': 'Bank Summary'}
    return codat_bank_statement_excel(bank_statement_response.json(), user_object, info)


def codat_bank_statement_excel(json_response, user_object, info):
    if not json_response or not json_response.get('results'):
        return False
    file_path = f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/' \
                f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
    if not os.path.exists(
            f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
            f'{settings.ON_BOARDING_DATA_FILE_PATH}/'):
        os.makedirs(f'{settings.MEDIA_ROOT}/{settings.ON_BOARDING_DATA_BASE_PATH}/{str(user_object.id)}/'
                    f'{settings.ON_BOARDING_DATA_FILE_PATH}/')

        # Saving data to a json file
        with open(f"file_path + {info['type']}.json", 'w') as f:
            json.dump(json_response['results'], f)

    df = pd.DataFrame()
    writer = pd.ExcelWriter(file_path + f"{info['type']}.xlsx", engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1')

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    # Add a header format.
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 11,
        'valign': 'vcenter',
        'fg_color': '#eeeeee',
        'align': 'center',
        'border': 1})
    # Add a section title format.
    section_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 10,
        'valign': 'bottom',
        'fg_color': '#bcbcbc',
        'border': 1})
    # Add a row title format.
    row_title_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 10,
        'valign': 'bottom',
        'fg_color': '#eeeeee',
        'border': 1})
    # Add a row format.
    row_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'font_size': 9,
        'valign': 'bottom',
        'fg_color': '#ffffff',
        'border': 1})
    worksheet.merge_range('A1:B1', info['title'], header_format)
    worksheet.merge_range('A2:B2', info['sub_title'], header_format)
    # worksheet.merge_range('A3:B3', json_response['Reports'][0]['ReportTitles'][2], header_format)

    row_data = json_response['results']
    row = 3
    worksheet.write(row, 0, 'Account', section_title_format)
    worksheet.write(row, 1, 'Balance', section_title_format)
    total = 0

    for data in row_data:
        row += 1
        worksheet.write(row, 0, data.get('accountName', ''), row_format)
        worksheet.write(row, 1, str(data.get('balance', '0.00')), row_format)
        total += data.get('balance', 0.0)
    row += 1
    worksheet.write(row, 0, 'Total', row_title_format)
    worksheet.write(row, 1, str(total), row_title_format)

    worksheet.set_column(0, 0, 45)
    worksheet.set_column(1, 1, 10)

    workbook.close()


def codat_sync_completed_mail(id, sme_name, user_id):
    """
    Function for sending email to the admin when codat data sync completed
    :param sme_name: sme name
    :return:
    """

    message = render_to_string('contacts_app/codat_sync_completed.html', {'sme_name': sme_name,
                                                                          'login_link': f'{settings.FRONTEND_URL}{settings.ONBOARD_VIEW}{str(id)}&role={settings.SME["name_value"]}&user_id={str(user_id)}',
                                                                          'logo_path': settings.BACKEND_URL[
                                                                                       :-1] + settings.MEDIA_URL + 'logo/'})
    send_email_utility(settings.CODAT_SYNC_COMPLETED, message, settings.ADMIN_EMAIL)


def password_reset_send_email(subject, model_instance, recipient_email):
    """
    Function for sending email to the reset the password link

    :param subject: subject of the email
    :param model_instance: model instance
    :param recipient_email: email id of recipient
    :return:
    """

    # Imported inside function to prevent circular import error
    from .utility import send_email_utility
    password_reset_link = f'{settings.FRONTEND_URL}{settings.FRONTEND_SIGN_UP_URL}{model_instance.slug_value}'
    message = render_to_string('registration/password_reset.html', {
        'instance_data': model_instance,
        'password_reset_link': password_reset_link,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/'
    })
    send_email_utility(subject, message, recipient_email)


def calculate_paid_amount(fund_invoice):
    """
        Function for getting paid amount for a fund invoice
        :param : object of fund invoice
        :return : paid amount
    """
    from transaction_app.models import PaymentModel, PAYMENT_TO_FACTORING_COMPANY_BY_SME

    paid_amount = PaymentModel.objects.filter(payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                              fund_invoice=fund_invoice,
                                              fund_invoice__is_deleted=False). \
                      aggregate(Sum('paying_amount')).get('paying_amount__sum') or 0
    return paid_amount


def disconnect_codat(company_id, connection_id):
    """
    Function for create company in codat
    """
    response = requests.delete(f"https://api.codat.io/companies/{company_id}/connections/{connection_id}",
                               headers={"Content-Type": "application/json",
                                        "Accept": "application/json",
                                        "Authorization": settings.CODAT_AUTHORIZATION_KEY})

    return response


def delete_codat_company(company_id):
    """
    Function for deleting a company in codat
    """
    response = requests.delete(f"https://api.codat.io/companies/{company_id}",
                               headers={"Content-Type": "application/json",
                                        "Accept": "application/json",
                                        "Authorization": settings.CODAT_AUTHORIZATION_KEY})

    return response
