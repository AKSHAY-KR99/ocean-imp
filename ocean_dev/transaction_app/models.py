from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.crypto import get_random_string
from django_countries.fields import CountryField
from django.db import IntegrityError
from contact_app.models import LeadsModel

from utils.model_utility import fund_invoice_files_path, contract_file_base_path, signed_contract_file_path, \
    payment_file_path, shipment_file_path, additional_shipment_file_path

# payment method choices data
PAYMENT_METHOD_BANK_TRANSFER = 1
# PAYMENT_METHOD_ONLINE_TRANSFER = 2
LETTER_OF_CREDIT = 2
PAYMENT_METHOD_CHOICES = ((PAYMENT_METHOD_BANK_TRANSFER, "BANK_TRANSFER"), (LETTER_OF_CREDIT,
                                                                            "LETTER_OF_CREDIT"))
# payment type choices
PAYMENT_TO_FACTORING_COMPANY_BY_SME = 1
PAYMENT_TO_SUPPLIER_BY_ADMIN = 2
PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY = 3
PAYMENT_TYPE_CHOICES = ((PAYMENT_TO_FACTORING_COMPANY_BY_SME, "PAYMENT_TO_FACTORING_COMPANY_BY_SME"),
                        (PAYMENT_TO_SUPPLIER_BY_ADMIN, "PAYMENT_TO_SUPPLIER_BY_ADMIN"),
                        (PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY, "PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY"))
# Payment status choices
# PAYMENT_STATUS_INITIATED = 1
# PAYMENT_STATUS_COMPLETED = 2
# PAYMENT_STATUS_ON_HOLD = 3
# PAYMENT_STATUS_CHOICES = ((PAYMENT_STATUS_INITIATED, "INITIATED"),
#                           (PAYMENT_STATUS_COMPLETED, "COMPLETED"),
#                           (PAYMENT_STATUS_ON_HOLD, "ON_HOLD"))

# Payment status action taken choices
CREDIT_PAYMENT_ADDED = 1
CREDIT_PAYMENT_RECEIVED_ACKNOWLEDGED = 2
CREDIT_PAYMENT_ON_HOLD_ACKNOWLEDGED = 3
PAYMENT_STATUS_ACTION_CHOICES = ((CREDIT_PAYMENT_ADDED, "PAYMENT_ADDED"),
                                 (CREDIT_PAYMENT_RECEIVED_ACKNOWLEDGED, "PAYMENT_RECEIVED_ACKNOWLEDGED"),
                                 (CREDIT_PAYMENT_ON_HOLD_ACKNOWLEDGED, "PAYMENT_ON_HOLD_ACKNOWLEDGED"))

# Payment acknowledgement status choices
CREDIT_PAYMENT_ACKNOWLEDGED = 1
CREDIT_PAYMENT_ACKNOWLEDGED_BY_ADMIN = 2
CREDIT_PAYMENT_ACKNOWLEDGED_BY_FACTOR = 3
CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING = 4
CREDIT_PAYMENT_PAID = 5
PAYMENT_ACKNOWLEDGMENT_STATUS_CHOICES = ((CREDIT_PAYMENT_ACKNOWLEDGED, "ACKNOWLEDGED"),
                                         (CREDIT_PAYMENT_ACKNOWLEDGED_BY_ADMIN, "ACKNOWLEDGED_BY_ADMIN"),
                                         (CREDIT_PAYMENT_ACKNOWLEDGED_BY_FACTOR, "ACKNOWLEDGED_BY_FACTOR"),
                                         (CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING, "PENDING"),
                                         (CREDIT_PAYMENT_PAID, "PAID"))

# Fund invoice Application status choices data
FUND_INVOICE_INITIATED = 1
FUND_INVOICE_APPROVED = 2
FUND_INVOICE_REJECTED = 3
FUND_INVOICE_STATUS_CHOICES = ((FUND_INVOICE_INITIATED, "INITIATED"),
                               (FUND_INVOICE_APPROVED, "APPROVED"),
                               (FUND_INVOICE_REJECTED, "REJECTED"))

# transport mode choices data
TRANSPORT_MODE_AIR = 1
TRANSPORT_MODE_SEA = 2
TRANSPORT_MODE_MIXED = 3
TRANSPORT_MODE_CHOICES = ((TRANSPORT_MODE_AIR, "AIR"), (TRANSPORT_MODE_SEA, "SEA"), (TRANSPORT_MODE_MIXED, "MIXED"))
TRANSPORT_MODE_MIXED_CHOICES = ((TRANSPORT_MODE_AIR, "AIR"), (TRANSPORT_MODE_SEA, "SEA"))

# Payment amount type choices data
TERMS_TYPE_PERCENTAGE = 1
TERMS_TYPE_AMOUNT = 2
TERMS_TYPE_BALANCE = 3
AMOUNT_TYPE_CHOICES = ((TERMS_TYPE_PERCENTAGE, "PERCENTAGE"), (TERMS_TYPE_AMOUNT, "AMOUNT"),
                       (TERMS_TYPE_BALANCE, "BALANCE"))

# Term criteria type choices data
TERMS_CRITERIA_DAYS_FROM_CONTRACT_SIGNATURE = 1
TERMS_CRITERIA_DAYS_FROM_LAST_PAYMENT = 2
TERMS_CRITERIA_CHOICES = ((TERMS_CRITERIA_DAYS_FROM_CONTRACT_SIGNATURE, "DAYS_FROM_CONTRACT_SIGNATURE"),
                          (TERMS_CRITERIA_DAYS_FROM_LAST_PAYMENT, "DAYS_FROM_LAST_PAYMENT"))

# Term criteria type choices data
INSTALLMENT_PERIOD_WEEKLY = 1
INSTALLMENT_PERIOD_MONTHLY = 2
INSTALLMENT_PERIOD_CHOICES = ((INSTALLMENT_PERIOD_WEEKLY, "WEEKLY"), (INSTALLMENT_PERIOD_MONTHLY, "MONTHLY"))

# Contract file type choices data
GENERATED_CONTRACT = 1
SME_SIGNED_CONTRACT = 2
ADMIN_SIGNED_CONTRACT = 3
CONTRACT_FILE_TYPE_CHOICES = ((GENERATED_CONTRACT, "GENERATED_CONTRACT"), (SME_SIGNED_CONTRACT, "SME_SIGNED_CONTRACT"),
                              (ADMIN_SIGNED_CONTRACT, "ADMIN_SIGNED_CONTRACT"))

# Signed contract file status choices data
SIGNED_CONTRACT_CREATED = 1
SIGNED_CONTRACT_DISABLED = 2
SIGNED_CONTRACT_ADDED = 3
SIGNED_CONTRACT_STATUS_CHOICES = ((SIGNED_CONTRACT_CREATED, "CREATED"), (SIGNED_CONTRACT_DISABLED, "OBSOLETE"),
                                  (SIGNED_CONTRACT_ADDED, "ACTIVE"))
# Contract category Choices
NEW_CONTRACT = 1
MASTER_CONTRACT = 2
CONTRACT_CATEGORY_CHOICES = ((NEW_CONTRACT, "NEW_CONTRACT"), (MASTER_CONTRACT, "MASTER_CONTRACT"))


class FundInvoiceModel(models.Model):
    """
    Model class for saving fund invoice data
    """
    sme = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="fund_invoice_sme")
    supplier = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="fund_invoice_supplier")
    invoice_total_amount = models.DecimalField(max_digits=20, decimal_places=3, default=0, blank=False)
    invoice_number = models.CharField(max_length=50, blank=False)
    invoice_date = models.DateField(blank=False, null=False)
    shipment_date = models.DateField(blank=True, null=True)
    currency_used = models.CharField(max_length=5, default="USD")
    assign_to = models.CharField(max_length=20, blank=True)
    application_status = models.PositiveSmallIntegerField(choices=FUND_INVOICE_STATUS_CHOICES, blank=True, null=True)
    transport_mode = models.PositiveSmallIntegerField(choices=TRANSPORT_MODE_CHOICES, blank=True, null=True)
    supplier_term = models.ForeignKey('PaymentTermModel', on_delete=models.SET_NULL, blank=True, null=True,
                                      related_name="invoice_supplier_terms")
    # destination_country = CountryField(blank=True, null=True)
    fixed_fee_value = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    contract_category = models.PositiveSmallIntegerField(choices=CONTRACT_CATEGORY_CHOICES, blank=True, null=True)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)
    date_approved = models.DateField(null=True)
    is_deleted = models.BooleanField(default=False)
    total_sales_amount = models.DecimalField(max_digits=20, null=True, decimal_places=3)
    factoring_company = models.ForeignKey('registration.User', on_delete=models.SET_NULL, null=True,
                                          related_name="invoice_factoring_company")
    gross_margin = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    markup = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
            self.application_status = FUND_INVOICE_INITIATED
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)


class FundInvoiceFilesModel(models.Model):
    """
    Model for storing the invoice files for invoice fund requested
    """
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.CASCADE, related_name="fund_invoice_files")
    file_object = models.FileField(upload_to=fund_invoice_files_path)

    def __str__(self):
        return str(self.file_object.url)


class FundInvoiceStatusModel(models.Model):
    """
    Model for storing the status related data of a FundInvoiceModel
    """
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.CASCADE, related_name="fund_invoice_status")
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="status_action_by")
    status_created_date = models.DateField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    action_taken = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.action_taken


class FundInvoiceCountryModel(models.Model):
    """
    Model for storing the origin, destination and shipping details of a FundInvoiceModel
    """
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.CASCADE, related_name="fund_invoice_country")
    shipping_date = models.DateField(blank=True, null=True)
    shipment_mode = models.PositiveSmallIntegerField(choices=TRANSPORT_MODE_MIXED_CHOICES, blank=True, null=True)
    origin_city = models.ForeignKey('cities_light.City', on_delete=models.CASCADE,
                                    related_name="fund_invoice_origin_city")
    origin_country = models.ForeignKey('cities_light.Country', on_delete=models.CASCADE,
                                       related_name="fund_invoice_origin_country")
    destination_city = models.ForeignKey('cities_light.City', on_delete=models.CASCADE,
                                         related_name="fund_invoice_destination_city")
    destination_country = models.ForeignKey('cities_light.Country', on_delete=models.CASCADE,
                                            related_name="fund_invoice_destination_country")
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return str(self.destination_country)


class PaymentTermModel(models.Model):
    """
    Model for storing the Payment Term details
    """
    name = models.CharField(max_length=250, blank=False)
    description = models.TextField(blank=True)
    status = models.BooleanField(default=True)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)
    for_sme = models.BooleanField(default=True)
    is_delete = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class SmeTermsAmountModel(models.Model):
    """
    Model for storing amount/percentage Terms for a Payment Term for SME
    """
    terms_label = models.CharField(max_length=200, blank=False)
    terms_order = models.IntegerField(blank=False)
    value = models.DecimalField(max_digits=10, decimal_places=2, blank=False)
    type = models.PositiveSmallIntegerField(choices=AMOUNT_TYPE_CHOICES, blank=True, null=True)
    days = models.IntegerField(blank=False)
    criteria = models.PositiveSmallIntegerField(choices=TERMS_CRITERIA_CHOICES, blank=True, null=True)
    payment_term = models.ForeignKey(PaymentTermModel, on_delete=models.CASCADE, related_name="sme_amount_terms")

    def __str__(self):
        return self.terms_label


class SmeTermsInstallmentModel(models.Model):
    """
    Model for storing installment type Terms for a Payment Term for SME
    """
    units = models.IntegerField(blank=False)
    period = models.PositiveSmallIntegerField(choices=INSTALLMENT_PERIOD_CHOICES, blank=True, null=True)
    payment_term = models.ForeignKey(PaymentTermModel, on_delete=models.CASCADE, related_name="sme_installment_terms")
    equal_installments = models.BooleanField(default=True)

    def __str__(self):
        return str(self.payment_term.id)


class SupplierTermsModel(models.Model):
    """
    Model for storing Terms for a Payment Term for Supplier
    """
    terms_label = models.CharField(max_length=100, blank=False)
    terms_order = models.IntegerField(blank=False)
    value = models.DecimalField(max_digits=10, decimal_places=2, blank=False)
    value_type = models.PositiveSmallIntegerField(choices=AMOUNT_TYPE_CHOICES, blank=True, null=True)
    payment_term = models.ForeignKey(PaymentTermModel, on_delete=models.CASCADE, related_name="supplier_terms")
    before_shipment = models.BooleanField(default=True)

    def __str__(self):
        return self.terms_label


class ContractTypeModel(models.Model):
    """
    Model for storing Contract Type
    """
    name = models.CharField(max_length=150, blank=False)
    description = models.TextField()
    gross_margin = models.DecimalField(max_digits=6, decimal_places=3)
    markup = models.DecimalField(max_digits=6, decimal_places=3)
    fixed_fee_type = models.PositiveSmallIntegerField(choices=AMOUNT_TYPE_CHOICES, blank=True, null=True)
    fixed_fee_value = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    payment_terms = models.ForeignKey(PaymentTermModel, on_delete=models.SET_NULL, related_name='payment_terms',
                                      null=True)
    status = models.BooleanField(default=True)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ContractModel(models.Model):
    """
    Model for storing contract details
    """
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.SET_NULL, null=True,
                                     related_name="contract_fund_invoice")
    factoring_company = models.ForeignKey('registration.User', on_delete=models.SET_NULL, null=True,
                                          blank=True, related_name="contract_factoring_company")
    contract_type = models.ForeignKey(ContractTypeModel, on_delete=models.CASCADE, related_name="contract_type")
    terms_conditions = models.TextField(null=True)
    additional_information = models.TextField(null=True)
    fixed_fee_value = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    contract_number = models.CharField(unique=True, null=False, max_length=50)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)
    is_master_contract = models.BooleanField(null=False, default=False)
    total_sales_amount = models.DecimalField(max_digits=20, null=True, decimal_places=3)
    gross_margin = models.DecimalField(max_digits=6, null=True, decimal_places=3)
    markup = models.DecimalField(max_digits=6, decimal_places=3, null=True)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        if self.fund_invoice is None:
            return str(self.id)
        else:
            return str(self.fund_invoice.id)


class ContractSupportingDocsModel(models.Model):
    """
    Model for storing the contract supporting docs
    """
    contract = models.ForeignKey(ContractModel, on_delete=models.CASCADE, related_name="supporting_docs")
    contract_file = models.FileField(upload_to=contract_file_base_path)

    def __str__(self):
        return str(self.contract_file.url)


class SignedContractFilesModel(models.Model):
    """
    Model for storing the contract files
    """
    contract = models.ForeignKey(ContractModel, on_delete=models.CASCADE, related_name="signed_contract_file")
    contract_doc_type = models.PositiveSmallIntegerField(choices=CONTRACT_FILE_TYPE_CHOICES, blank=True, null=True)
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="signed_by")
    file_path = models.CharField(max_length=150, blank=True)
    file_status = models.PositiveSmallIntegerField(choices=SIGNED_CONTRACT_STATUS_CHOICES, blank=True, null=True)
    reminder_count = models.IntegerField(null=True)
    reminder_sending_time = models.DateTimeField(auto_now=True, null=True)
    date_modified = models.DateField(null=True)

    class Meta:
        ordering = ['-id']
    
    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if self.id:
            self.date_modified = date_value
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.file_path


class ShipmentModel(models.Model):
    """
    Model for storing the shipment details
    """
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.CASCADE, related_name="shipment_fund_invoice")
    shipment_date = models.DateField(blank=True, null=True)
    number_of_shipments = models.IntegerField(blank=False)
    other_info = models.CharField(max_length=200, blank=True)
    system_remarks = models.TextField(blank=True)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)


class ShipmentFilesModel(models.Model):
    """
    Model for storing the shipment files
    """
    country = models.ForeignKey(FundInvoiceCountryModel, on_delete=models.CASCADE, related_name="shipment_country")
    shipment = models.ForeignKey(ShipmentModel, on_delete=models.CASCADE, related_name="shipment_files")
    shipment_number = models.IntegerField(blank=False)
    document_type = models.CharField(max_length=200, choices=settings.SHIPMENT_DOCUMENTS, default=settings.INVOICE)
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="shipment_action_by")
    file_object = models.FileField(upload_to=shipment_file_path)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return str(self.file_object.url)


class AdditionalShipmentFilesModel(models.Model):
    """
    Model for storing the shipment files
    """
    shipment = models.ForeignKey(ShipmentModel, on_delete=models.CASCADE, related_name="additional_shipment_files")
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="action_by")
    additional_shipment_file = models.FileField(upload_to=additional_shipment_file_path)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return str(self.additional_shipment_file.url)


class PaymentModel(models.Model):
    """
    Model for storing payment data
    """
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.CASCADE, related_name="payment_fund_invoice")
    paying_amount = models.DecimalField(max_digits=20, decimal_places=3)
    payment_method = models.PositiveSmallIntegerField(choices=PAYMENT_METHOD_CHOICES, blank=False, null=False)
    # payment_status = models.PositiveSmallIntegerField(choices=PAYMENT_STATUS_CHOICES, default=1)
    payment_ref_number = models.CharField(max_length=50, blank=True, null=True)
    payment_remarks = models.TextField()
    payment_date = models.DateField(null=True, blank=True)
    payment_made_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="payment_user")
    payment_type = models.PositiveSmallIntegerField(choices=PAYMENT_TYPE_CHOICES, blank=False, null=False)
    acknowledgement_status = models.PositiveSmallIntegerField(choices=PAYMENT_ACKNOWLEDGMENT_STATUS_CHOICES,
                                                              blank=False, null=False)
    acknowledgement_completed = models.BooleanField(default=False)
    is_adhoc = models.BooleanField(default=False)
    tax_amount = models.DecimalField(max_digits=20, decimal_places=3)
    term_order = models.IntegerField(default=1)
    system_remarks = models.TextField(blank=True)
    date_created = models.DateField(null=True)
    date_modified = models.DateField(null=True)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        date_value = timezone.now().date()
        if not self.id:
            self.date_created = date_value
        self.date_modified = date_value
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.fund_invoice.id) + '_' + str(self.payment_type) + '_' + str(self.term_order)


class PaymentFilesModel(models.Model):
    """
    Model for storing the contract files
    """
    payment = models.ForeignKey(PaymentModel, on_delete=models.CASCADE, related_name="payment_files")
    payment_file = models.FileField(upload_to=payment_file_path)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return str(self.payment_file.url)


class PaymentStatusModel(models.Model):
    """
    Model for storing the status related data of a PaymentModel
    """
    payment = models.ForeignKey(PaymentModel, on_delete=models.CASCADE, related_name="payment_status_data")
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="payment_action_by")
    status_created_date = models.DateField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    action_taken = models.PositiveSmallIntegerField(choices=PAYMENT_STATUS_ACTION_CHOICES, blank=False, null=False)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return str(self.id)


class MasterContractStatusModel(models.Model):
    """
    Model for storing the status related data of a MModel
    """
    contract = models.ForeignKey(ContractModel, on_delete=models.CASCADE, related_name="master_contract_status")
    action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="action_by_user")
    status_created_date = models.DateField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    action_taken = models.CharField(max_length=100, blank=True)
    assign_to = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.action_taken


class AccountDetailsModel(models.Model):
    """
    Model for storing the account details valkin 
    """
    account_no = models.CharField(max_length=100, null=False)
    sort_code = models.CharField(max_length=50, null=False)
    sterling = models.CharField(max_length=50, null=True)
    euros = models.CharField(max_length=50, null=True)
    us_dollar = models.CharField(max_length=50, null=True)

    def __str__(self):
        return self.account_no


class ContractAdditionalCostType(models.Model):
    """
    Model for adding addition cost type in contract creation
    """
    additional_cost_type = models.CharField(max_length=20, blank=False, null=False)

    def __str__(self):
        return self.additional_cost_type


class AdditionalContractCost(models.Model):
    """
    Model for saving additional cost details
    """
    contract = models.ForeignKey(ContractModel, on_delete=models.CASCADE, related_name='additional_contract_cost')
    additional_cost_type = models.ForeignKey(ContractAdditionalCostType, on_delete=models.CASCADE,
                                             related_name='additional_contract_cost_type')
    additional_cost_value = models.DecimalField(max_digits=10, decimal_places=3, blank=False, null=False)

    def __str__(self):
        return str(self.contract)
    
class NotificationModel(models.Model):
    """
    Model for storing the notification details 
    """
    user = models.ForeignKey('registration.User', on_delete=models.SET_NULL, null=True, related_name="user_notification")
    lead_user = models.ForeignKey(LeadsModel, on_delete=models.SET_NULL, null=True, related_name="lead_user_notification")
    on_boarding_details = models.ForeignKey('registration.UserDetailModel', on_delete=models.SET_NULL, 
                                             null=True, related_name="user_details")
    fund_invoice = models.ForeignKey(FundInvoiceModel, on_delete=models.SET_NULL, null=True, related_name="notification_fund_invoice")
    contract = models.ForeignKey(ContractModel, on_delete=models.SET_NULL, null=True, related_name="notification_contract")    
    shipment = models.ForeignKey(ShipmentModel, on_delete=models.SET_NULL, null=True, related_name="notification_shipment")
    is_read = models.BooleanField(default=False)
    assignee = models.ForeignKey('registration.User', on_delete=models.SET_NULL, null=True, related_name="assigned_user")
    notification = models.TextField(max_length=100)
    type = models.CharField(max_length=50)   
    description = models.TextField(max_length=100)
    is_completed = models.BooleanField(default=False)   
    is_deleted = models.BooleanField(default=False)
    date = models.DateField(auto_now=True)
    
# class SigningRemainderModel(models.Model):
#     """
#     Model for storing the details of a sme remainder
#     """
#     sending_time = models.DateTimeField(auto_now=True)
#     count = models.IntegerField()
#     contract = models.ForeignKey(ContractModel, on_delete=models.CASCADE, related_name="sme_remainder_contract")

#     class Meta:
#         ordering = ['-id']

# old code
#
# class RequestModel(models.Model):
#     """
#     Model class for Request Table
#     """
#     sme = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="request_sme")
#     supplier = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="request_supplier")
#     credit_amount = models.DecimalField(max_digits=20, decimal_places=3, default=0, blank=False)
#     purpose = models.CharField(max_length=100, blank=True)
#     status_stage = models.CharField(max_length=100, blank=True)
#     assign_to = models.CharField(max_length=100, blank=True)
#     status_stage_completed = models.BooleanField(default=False)
#     currency_used = models.CharField(max_length=5, default="USD")
#     applied_date = models.DateField(auto_now_add=True)
#     rejected_status = models.BooleanField(default=False)
#     credit_returned = models.BooleanField(default=False)
#
#     class Meta:
#         ordering = ['-id']
#
#     def __str__(self):
#         return str(self.sme.first_name) + ' | ' + str(self.purpose)
#
#
# class SupportingDocsModel(models.Model):
#     """
#     Model for storing the supporting docs for a request applied
#     """
#     request = models.ForeignKey(RequestModel, on_delete=models.CASCADE, related_name="request_supporting_docs")
#     file_path = models.CharField(max_length=200, help_text="Base path for SupportingDocsModel files", default='')
#     supporting_doc = models.FileField(upload_to=supporting_doc_base_path)
#
#     def __str__(self):
#         return str(self.supporting_doc.url)
#
#
# class RequestStatusModel(models.Model):
#     """
#     Model for storing the status related data of a RequestModel
#     """
#     request = models.ForeignKey(RequestModel, on_delete=models.CASCADE, related_name="request_status")
#     action_by = models.ForeignKey('registration.User', on_delete=models.CASCADE, related_name="status_action_by")
#     status_created_date = models.DateField(auto_now_add=True)
#     status_stage = models.CharField(max_length=100, blank=True)
#     remarks = models.CharField(max_length=100, blank=True)
#     status = models.CharField(max_length=100, blank=True)
#
#     class Meta:
#         ordering = ['-id']
#
#     def __str__(self):
#         return self.status
#
#
# class RequestInvoiceModel(models.Model):
#     """
#     Model for storing the credit request invoices
#     """
#     request = models.ForeignKey(RequestModel, on_delete=models.CASCADE, related_name="request_invoice")
#     invoice_number = models.CharField(max_length=50, blank=True)
#     invoice_date = models.DateField(blank=True, null=True)
#     shipment_date = models.DateField(blank=True, null=True)
#     total_amount = models.DecimalField(max_digits=20, decimal_places=3, default=0, blank=False)
#     total_vat = models.DecimalField(max_digits=20, decimal_places=3, default=0, blank=True)
#     grand_total = models.DecimalField(max_digits=20, decimal_places=3, default=0, blank=False)
#     invoice_status = models.BooleanField(default=False)
#
#     class Meta:
#         ordering = ['-id']
#
#     def __str__(self):
#         return str(self.request.id)
#
#
# class InvoiceFilesModel(models.Model):
#     """
#     Model for storing the invoice files for a request applied
#     """
#     invoice = models.ForeignKey(RequestInvoiceModel, on_delete=models.CASCADE, related_name="invoice_files")
#     invoice_file_path = models.CharField(max_length=200, help_text="Base path for InvoiceFilesModel files", default='')
#     invoice_file = models.FileField(upload_to=invoice_base_path)
#
#     def __str__(self):
#         return str(self.invoice_file.url)
