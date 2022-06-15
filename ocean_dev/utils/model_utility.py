from django.conf import settings
from django.template.loader import render_to_string


def lead_send_email(subject, model_instance, recipient_email):
    """
    Function for sending email to the admin email(on adding a new data in LeadsModel)

    :param subject: subject of the email
    :param model_instance: model instance
    :param recipient_email: email id of recipient
    :return:
    """
    # Imported inside function to prevent circular import error
    from .utility import send_email_utility
    message = render_to_string('contacts_app/leads_info.html', {'leads_data': model_instance,
                                                                'logo_path': settings.BACKEND_URL[
                                                                             :-1] + settings.MEDIA_URL + 'logo/'})
    send_email_utility(subject, message, recipient_email)


# def contact_send_email(subject, model_instance, recipient_email):
#     """
#     Function for sending email to the admin email(on adding a new data in ContactModel)
#
#     :param subject: subject of the email
#     :param model_instance: model instance
#     :param recipient_email: email id of recipient
#     :return:
#     """
#     # Imported inside function to prevent circular import error
#     from .utility import send_email_utility
#     message = render_to_string('contacts_app/contact_info.html', {'contact_data': model_instance})
#     send_email_utility(subject, message, recipient_email, settings.EMAIL_HOST_USER)


def user_created_send_email(subject, model_instance, recipient_email):
    """
    Function for sending email to the newly created(by admin) user(on adding a new data in User model)

    :param subject: subject of the email
    :param model_instance: model instance
    :param recipient_email: email id of recipient
    :return:
    """

    # Imported inside function to prevent circular import error
    from .utility import send_email_utility
    registration_link = f'{settings.FRONTEND_URL}{settings.FRONTEND_SIGN_UP_URL}{model_instance.slug_value}'
    message = render_to_string('registration/user_created.html', {
        'instance_data': model_instance,
        'registration_link': registration_link,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/'
    })
    send_email_utility(subject, message, recipient_email)


def user_detail_base_path(instance, file_name):
    """
    Function for getting the instances (UserDetailModel) upload base path

    :param file_name: name of the file
    :param instance: model instance
    :return: file path
    """
    return str(instance.user_detail_path) + str(file_name)


def user_detail_id_base_path(instance, file_name):
    """
    Function for getting the instances (UserDetailFilesModel) upload base path

    :param file_name: name of the file
    :param instance: model instance
    :return: file path
    """
    return str(instance.detail.user_detail_path) + str(file_name)


def contract_file_base_path(instance, file_name):
    """
    Function for getting the instances (ContractSupportingDocsModel) upload base path

    :param file_name: name of the file
    :param instance: model instance
    :return: file path
    """
    file_path = f'{settings.FUND_INVOICE_DATA}/{str(instance.contract.fund_invoice.id)}/' \
                f'{settings.CONTRACT_SUPPORTING_DOCS}/'
    return str(file_path) + str(file_name)


def signed_contract_file_path(instance, file_name):
    """
    Function for getting the instances (ContractFilesModel) upload base path

    :param instance: model instance
    :param file_name: name of the file
    :return: file path
    """
    file_path = f'{settings.FUND_INVOICE_DATA}/{str(instance.contract.fund_invoice.id)}/' \
                f'{settings.SIGNED_CONTRACT_FILES}/'
    return str(file_path) + str(file_name)


def fund_invoice_files_path(instance, file_name):
    """
    Function for getting the instances (FundInvoiceModel) upload base path

    :param file_name: name of the file
    :param instance: model instance
    :return: file path
    """
    file_path = f'{settings.FUND_INVOICE_DATA}/{str(instance.fund_invoice.id)}/{settings.FUND_INVOICE_FILES}/'
    return str(file_path) + str(file_name)


def payment_file_path(instance, file_name):
    """
    Function for getting the instances (PaymentFilesModel) upload base path

    :param file_name: name of the file
    :param instance: model instance
    :return: file path
    """
    file_path = f'{settings.FUND_INVOICE_DATA}/{str(instance.payment.fund_invoice.id)}/{settings.PAYMENT_FILES}/' \
                f'{instance.payment.id}/'
    return str(file_path) + str(file_name)


def shipment_file_path(instance, file_name):
    """
    Function for getting the instances (ShipmentFilesModel) upload base path

    :param instance: model instance
    :param file_name: name of the file
    :return: file path
    """
    file_path = f'{settings.FUND_INVOICE_DATA}/{str(instance.shipment.fund_invoice.id)}/{settings.SHIPMENT_FILES}/'
    return str(file_path) + str(file_name)


def additional_shipment_file_path(instance, file_name):
    """
    Function for getting the instances (AdditionalShipmentFilesModel) upload base path

    :param instance: model instance
    :param file_name: name of the file
    :return: file path
    """
    file_path = f'{settings.FUND_INVOICE_DATA}/{str(instance.shipment.fund_invoice.id)}/{settings.ADDITIONAL_SHIPMENT_FILES}/'
    return str(file_path) + str(file_name)


def profile_image_path(instance, file_name):
    """
    Function for getting the instances (UserModel) upload base path

    :param instance: model instance
    :param file_name: name of the file
    :return: file path
    """
    file_path = f'user/{str(instance.id)}/'
    return str(file_path) + str(file_name)


def xero_file_path(instance, file_name):
    """
    Function for getting the instances upload base path

    :param file_name: name of the file
    :param instance: model instance
    :return: file path
    """
    file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(instance.user.id)}/{settings.XERO_FILES_PATH}/'
    return str(file_path) + str(file_name)


def send_lead_rejected_email(subject, model_instance, recipient_email):
    """
    Function for sending email to the lead user email(rejected case)

    :param subject: subject of the email
    :param model_instance: model instance
    :param recipient_email: email id of recipient
    :return:
    """
    # Imported inside function to prevent circular import error
    from .utility import send_email_utility
    message = render_to_string('contacts_app/leads_rejected.html', {'leads_data': model_instance,
                                                                    'logo_path': settings.BACKEND_URL[
                                                                                 :-1] + settings.MEDIA_URL + 'logo/'})
    send_email_utility(subject, message, recipient_email)


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
    password_reset_link = f'{settings.FRONTEND_URL}{settings.FRONTEND_PASSWORD_RESET_URL}'
    message = render_to_string('registration/password_reset.html', {
        'instance_data': model_instance,
        'password_reset_link': password_reset_link,
        'logo_path': settings.BACKEND_URL[:-1] + settings.MEDIA_URL + 'logo/'
    })
    send_email_utility(subject, message, recipient_email)
# old code
# def supporting_doc_base_path(instance, file_name):
#     """
#     Function for getting the instances (SupportingDocsModel) upload base path
#
#     :param file_name: name of the file
#     :param instance: model instance
#     :return: file path
#     """
#     return str(instance.file_path) + str(file_name)
#
#
# def invoice_base_path(instance, file_name):
#     """
#     Function for getting the instances (RequestInvoiceModel) upload base path
#
#     :param file_name: name of the file
#     :param instance: model instance
#     :return: file path
#     """
#     return str(instance.invoice_file_path) + str(file_name)
