import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from numpy import source
from rest_framework import serializers
from contact_app import models as contact_app_models
from utils.utility import generate_request_next_step, list_contract_next_step, list_payment_next_step, \
    get_shipment_warning_message, next_step_based_on_contract_category, calculate_paid_amount
from django_countries.serializers import CountryFieldMixin
from . import models
from django.db.models import Sum, Q
from .models import ContractModel, FundInvoiceModel
from cities_light.models import City, Country
from datetime import datetime, timedelta
from django_countries import countries
import calendar

User = get_user_model()


class ChoiceFieldSerializer(serializers.ChoiceField):
    """
    Class for generating the actual string value from the choice numbers
    """

    def to_representation(self, obj):
        if obj == '' and self.allow_blank:
            return obj
        return self._choices[obj]


class FundInvoiceStatusModelSerializer(serializers.ModelSerializer):
    """
    Serializer class for FundInvoiceStatusModel
    """
    action_by_user_name = serializers.CharField(source='action_by.first_name', read_only=True)

    class Meta:
        model = models.FundInvoiceStatusModel
        fields = ['fund_invoice', 'action_by', 'action_by_user_name', 'remarks', 'status_created_date', 'action_taken']
        extra_kwargs = {'fund_invoice': {"write_only": True}}


class FundInvoiceCountryModelSerializer(serializers.ModelSerializer):
    """
    Serializer class for FundInvoiceCountryModel
    """
    origin_city_name = serializers.CharField(source='origin_city.name', read_only=True)
    origin_display_name = serializers.CharField(source='origin_city.display_name', read_only=True)
    origin_country_code = serializers.CharField(source='origin_country.code2', read_only=True)
    destination_city_name = serializers.CharField(source='destination_city.name', read_only=True)
    destination_display_name = serializers.CharField(source='destination_city.display_name', read_only=True)
    destination_country_code = serializers.CharField(source='destination_country.code2', read_only=True)
    shipment_mode = ChoiceFieldSerializer(choices=models.TRANSPORT_MODE_MIXED_CHOICES, required=False)

    class Meta:
        model = models.FundInvoiceCountryModel
        fields = ['id', 'fund_invoice', 'shipping_date', 'shipment_mode', 'origin_city', 'origin_city_name',
                  'origin_display_name', 'origin_country', 'origin_country_code', 'destination_city',
                  'destination_city_name', 'destination_display_name', 'destination_country',
                  'destination_country_code', 'is_deleted']
        extra_kwargs = {'fund_invoice': {"write_only": True, "required": False}, 'is_deleted': {"read_only": True},
                        'origin_country': {"read_only": True}, 'origin_city': {"required": True},
                        'destination_country': {"read_only": True}, 'destination_city': {"required": True}}

    def validate(self, data):
        if data['origin_city'] == data['destination_city']:
            raise serializers.ValidationError("No same origin_city and destination_city are allowed.")
        return data

    def create(self, validated_data):
        fund_invoice_country_model = models.FundInvoiceCountryModel.objects.create(
            **validated_data, destination_country=validated_data['destination_city'].country,
            origin_country=validated_data['origin_city'].country, fund_invoice=self.context['fund_invoice'])
        return fund_invoice_country_model

    def update(self, instance, validated_data):
        instance.shipping_date = validated_data['shipping_date']
        instance.shipment_mode = validated_data['shipment_mode']
        instance.origin_city = validated_data['origin_city']
        instance.origin_country = validated_data['origin_city'].country
        instance.destination_city = validated_data['destination_city']
        instance.destination_country = validated_data['destination_city'].country
        instance.save()
        return instance


class ShipmentFilesModelSerializer(serializers.ModelSerializer):
    """
    Serializer for ShipmentFilesModel
    """
    file_object_url = serializers.CharField(source='file_object.url', read_only=True)

    class Meta:
        model = models.ShipmentFilesModel
        fields = ['id', 'shipment', 'country', 'shipment_number', 'document_type', 'action_by', 'file_object',
                  'file_object_url']
        extra_kwargs = {'file_object': {"write_only": True}}


class AdditionalShipmentFilesModelSerializer(serializers.ModelSerializer):
    """
    Serializer class for AdditionalShipmentFiles
    """
    additional_shipment_file_url = serializers.CharField(source='additional_shipment_file.url', read_only=True)

    class Meta:
        model = models.AdditionalShipmentFilesModel
        fields = ['shipment', 'action_by', 'additional_shipment_file', 'additional_shipment_file_url']
        extra_kwargs = {'additional_shipment_file': {"write_only": True}}


class ShipmentModelSerializer(serializers.ModelSerializer):
    """
    Serializers for ShipmentModel
    """
    # shipment_files = ShipmentFilesModelSerializer(many=True, read_only=True)
    additional_shipment_files = serializers.StringRelatedField(many=True, read_only=True)
    invoice_number = serializers.CharField(source='fund_invoice.invoice_number', read_only=True)

    class Meta:
        model = models.ShipmentModel
        fields = ['id', 'invoice_number', 'shipment_date', 'fund_invoice', 'number_of_shipments', 'other_info',
                  'date_created', 'date_modified', 'additional_shipment_files', 'system_remarks']
        extra_kwargs = {'system_remarks': {"write_only": True}}

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        response_data['shipment_files'] = FundInvoiceCountryModelSerializer(instance.fund_invoice.
            fund_invoice_country.filter(
            is_deleted=False), many=True).data
        for ind, data in enumerate(response_data['shipment_files']):
            file_obj = models.ShipmentFilesModel.objects.filter(country=data['id'])
            data['files'] = []
            for file_data in ShipmentFilesModelSerializer(file_obj, many=True).data:
                if file_data['document_type'] == 'additional_doc':
                    if file_data['document_type'] not in data:
                        data[file_data['document_type']] = []
                    data[file_data['document_type']].append(file_data['file_object_url'])
                else:
                    data['files'].append({'document_type': file_data['document_type'],
                                          'file_object_url': file_data['file_object_url']})
        response_data['fund_invoice_status'] = FundInvoiceStatusModelSerializer(instance.fund_invoice.
                                                                                fund_invoice_status, many=True).data
        next_step = generate_request_next_step(response_data['fund_invoice_status'][0]['action_taken'],
                                               self.context['request'].user.get_user_role_display())
        response_data['next_step'] = next_step

        return response_data


class SmeTermsAmountModelSerializer(serializers.ModelSerializer):
    """
    Serializer for SME Terms
    """
    type = ChoiceFieldSerializer(choices=models.AMOUNT_TYPE_CHOICES)
    criteria = ChoiceFieldSerializer(choices=models.TERMS_CRITERIA_CHOICES)

    class Meta:
        model = models.SmeTermsAmountModel
        fields = ['id', 'terms_label', 'terms_order', 'value', 'type', 'days', 'criteria', 'payment_term']


class SmeTermsInstallmentModelSerializer(serializers.ModelSerializer):
    """
    Serializer for SME Terms
    """
    period = ChoiceFieldSerializer(choices=models.INSTALLMENT_PERIOD_CHOICES)

    class Meta:
        model = models.SmeTermsInstallmentModel
        fields = ['id', 'units', 'period', 'equal_installments', 'payment_term']

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        if self.context.get("fund_invoice_id") is not None:
            fund_invoice = models.FundInvoiceModel.objects.get(id=self.context.get("fund_invoice_id"))
            if fund_invoice is not None and fund_invoice.total_sales_amount is not None:
                response_data['Amount_to_be_paid'] = round((fund_invoice.total_sales_amount / instance.units), 2)
        elif self.context.get("contract_id") is not None:
            contract = models.ContractModel.objects.get(id=self.context.get("contract_id"))
            if contract is not None and contract.total_sales_amount is not None:
                response_data['Amount_to_be_paid'] = round((contract.total_sales_amount / instance.units), 2)

        return response_data


class SupplierTermsModelSerializer(serializers.ModelSerializer):
    """
    Serializer for Supplier Terms
    """
    value_type = ChoiceFieldSerializer(choices=models.AMOUNT_TYPE_CHOICES)

    class Meta:
        model = models.SupplierTermsModel
        fields = ['id', 'terms_label', 'terms_order', 'value', 'value_type', 'before_shipment', 'payment_term']


class PaymentTermModelSerializer(serializers.ModelSerializer):
    """
    Serializer for PaymentTermModel
    """

    class Meta:
        model = models.PaymentTermModel
        fields = ['id', 'name', 'description', 'status', 'date_created', 'date_modified', 'for_sme', 'is_delete']

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        response_data['is_editable'] = False
        term_object = get_object_or_404(models.PaymentTermModel, id=response_data['id'])
        if not term_object.for_sme:
            if term_object.invoice_supplier_terms.all().count() == 0:
                response_data['is_editable'] = True
        else:
            if term_object.payment_terms.all().count() == 0:
                response_data['is_editable'] = True
        if response_data['for_sme']:
            if instance.sme_amount_terms.all():
                response_data['by_installment'] = False
                response_data['terms'] = SmeTermsAmountModelSerializer(instance.sme_amount_terms.all(), many=True).data
            else:
                response_data['by_installment'] = True
                if self.context.get("fund_invoice_id") is not None:
                    response_data['terms'] = SmeTermsInstallmentModelSerializer(instance.sme_installment_terms.all(),
                                                                                context={
                                                                                    "fund_invoice_id": self.context.get(
                                                                                        "fund_invoice_id")},
                                                                                many=True).data
                else:
                    response_data['terms'] = SmeTermsInstallmentModelSerializer(instance.sme_installment_terms.all(),
                                                                                context={
                                                                                    "contract_id": self.context.get(
                                                                                        "contract_id")},
                                                                                many=True).data

        else:
            response_data['terms'] = SupplierTermsModelSerializer(instance.supplier_terms.all(), many=True).data
        return response_data


class ContractTypeModelSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractTypeModel
    """
    fixed_fee_type = ChoiceFieldSerializer(choices=models.AMOUNT_TYPE_CHOICES, required=False)

    class Meta:
        model = models.ContractTypeModel
        fields = ['id', 'name', 'description', 'gross_margin', 'markup', 'fixed_fee_type', 'fixed_fee_value',
                  'status', 'date_modified', 'payment_terms', 'is_deleted']

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        contract_objects = models.ContractModel.objects.filter(contract_type=response_data['id'])
        response_data['is_editable'] = True
        if contract_objects.exists():
            response_data['is_editable'] = False
        if self.context.get("contract_id") is not None:
            contract_obj = models.ContractModel.objects.filter(id=self.context.get("contract_id"))
            if contract_obj.exists() and contract_obj.first().gross_margin and contract_obj.first().markup is not None:
                response_data['gross_margin'] = contract_obj.first().gross_margin
                response_data['markup'] = contract_obj.first().markup
        return response_data


class ContractSupportingDocsSerializers(serializers.ModelSerializer):
    """
    Serializer class for ContractSupportingDocsModel
    """

    class Meta:
        model = models.ContractSupportingDocsModel
        fields = ['contract', 'contract_file']
        extra_kwargs = {'contract': {"write_only": True}}


class AdditionalContractCostSerializer(serializers.ModelSerializer):
    """
    Serializer for additional cost details
    """

    class Meta:
        model = models.AdditionalContractCost
        fields = ['additional_cost_type', 'additional_cost_value']

        extra_kwargs = {'contract': {"required": False}}

    def create(self, validated_data):
        additional_cost_model = models.AdditionalContractCost.objects.create(
            **validated_data, contract=self.context['contract'])
        return additional_cost_model


class ContractModelSerializer(serializers.ModelSerializer):
    """
    Serializers for ContractModel
    """
    supporting_docs = serializers.StringRelatedField(many=True, read_only=True)
    sme_company_name = serializers.CharField(source='fund_invoice.sme.on_boarding_details.company_name',
                                             read_only=True)
    supplier_company_name = serializers.CharField(source='fund_invoice.supplier.on_boarding_details.company_name',
                                                  read_only=True)
    invoice_number = serializers.CharField(source='fund_invoice.invoice_number', read_only=True)
    factoring_company_name = serializers.CharField(source='factoring_company.first_name', read_only=True)

    master_contract_sme_company_name = serializers.CharField(
        source='sme_master_contract.on_boarding_details.company_name',
        read_only=True)

    class Meta:
        model = models.ContractModel
        fields = ['id', 'sme_company_name', 'supplier_company_name', 'contract_number', 'fund_invoice',
                  'factoring_company', 'factoring_company_name', 'contract_type', 'invoice_number',
                  'terms_conditions', 'additional_information', 'date_modified', 'date_created', 'supporting_docs',
                  'is_master_contract', 'master_contract_sme_company_name', 'fixed_fee_value', 'total_sales_amount',
                  'gross_margin', 'markup']

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        next_step = None
        if instance.is_master_contract:
            response_data['master_contract_status'] = MasterContractStatusSerializers(instance.master_contract_status,
                                                                                      many=True).data
            next_step = list_contract_next_step(response_data['master_contract_status'][0]['action_taken'],
                                                self.context['request'].user.get_user_role_display())
        else:
            response_data['fund_invoice_status'] = FundInvoiceStatusModelSerializer(instance.fund_invoice.
                                                                                    fund_invoice_status, many=True).data
            shipment_object = instance.fund_invoice.shipment_fund_invoice.all()
            if shipment_object.exists():
                response_data['shipment_id'] = shipment_object[0].id
            next_step = list_contract_next_step(response_data['fund_invoice_status'][0]['action_taken'],
                                                self.context['request'].user.get_user_role_display())
        response_data['additional_cost_data'] = AdditionalContractCostSerializer(
            models.AdditionalContractCost.objects.filter(contract=instance.id),
            many=True).data
        response_data['next_step'] = next_step
        reminder_interval = datetime.now()

        contract_obj = models.ContractModel.objects.filter(signed_contract_file__contract_doc_type=
                                                           models.ADMIN_SIGNED_CONTRACT,
                                                           id=instance.id,
                                                           signed_contract_file__reminder_sending_time__lt=
                                                           reminder_interval).exclude(
            signed_contract_file__contract_doc_type=
            models.SME_SIGNED_CONTRACT)
        if contract_obj.exists() and self.context['request'].user.get_user_role_display() == \
                settings.ADMIN["name_value"]:
            response_data["is_reminder_enabled"] = True
        else:
            response_data["is_reminder_enabled"] = False
        # if instance.factoring_company is None:
        #     response_data['factoring_company'] = 'None'
        return response_data


class SignedContractFilesSerializer(serializers.ModelSerializer):
    """
    Serializers for SignedContractFilesModel Model
    """
    action_by_user_role = serializers.CharField(source='action_by.user_role', read_only=True)
    contract_doc_type = ChoiceFieldSerializer(choices=models.CONTRACT_FILE_TYPE_CHOICES)
    file_status = ChoiceFieldSerializer(choices=models.SIGNED_CONTRACT_STATUS_CHOICES)

    class Meta:
        model = models.SignedContractFilesModel
        fields = ['contract', 'action_by', 'contract_doc_type', 'action_by_user_role', 'file_path', 'file_status']
        extra_kwargs = {'contract': {"write_only": True}}

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        response_data['file'] = f'{settings.MEDIA_URL}{response_data["file_path"]}'
        return response_data


class FundInvoiceFilesModelSerializers(serializers.ModelSerializer):
    """
    Serializer class for FundInvoiceFilesModel
    """

    class Meta:
        model = models.FundInvoiceFilesModel
        fields = ['fund_invoice', 'file_object', 'file_path']
        extra_kwargs = {'fund_invoice': {"write_only": True}, 'file_path': {"write_only": True}}


class FundInvoiceModelSerializer(CountryFieldMixin, serializers.ModelSerializer):
    """
    Serializer class for FundInvoiceModel
    """
    supplier_company_name = serializers.CharField(source='supplier.on_boarding_details.company_name', read_only=True)
    supplier_email = serializers.CharField(source='supplier.email', read_only=True)
    sme_company_name = serializers.CharField(source='sme.on_boarding_details.company_name', read_only=True)
    fund_invoice_files = serializers.StringRelatedField(many=True, read_only=True)
    fund_invoice_status = FundInvoiceStatusModelSerializer(many=True, read_only=True)
    fund_invoice_country = FundInvoiceCountryModelSerializer(many=True, read_only=True)
    transport_mode = ChoiceFieldSerializer(choices=models.TRANSPORT_MODE_CHOICES)
    contract_fund_invoice = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
    shipment_fund_invoice = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
    application_status = ChoiceFieldSerializer(choices=models.FUND_INVOICE_STATUS_CHOICES, read_only=True)
    # fixed_fee_value = serializers.CharField(source='sme.master_contract.contract_type.fixed_fee_value', read_only=True)

    class Meta:
        model = models.FundInvoiceModel
        fields = ['id', 'sme', 'sme_company_name', 'supplier', 'supplier_company_name', 'invoice_total_amount',
                  'transport_mode', 'currency_used', 'invoice_number', 'invoice_date', 'assign_to', 'shipment_date',
                  'application_status', 'date_created', 'date_modified', 'fund_invoice_files', 'fund_invoice_status',
                  'fund_invoice_country', 'supplier_email', 'contract_fund_invoice', 'shipment_fund_invoice',
                  'supplier_term', 'contract_category', 'total_sales_amount', 'factoring_company', 'gross_margin',
                  'markup', 'fixed_fee_value']

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        # response_data['credit_amount'] = convert_currency_value(response_data['currency_stored'],
        #                                                         response_data['currency_used'],
        #                                                         response_data['credit_amount'])
        supplier_leads_object = contact_app_models.LeadsModel.objects.filter(
            sign_up_email=response_data['supplier_email'])
        next_action_data = generate_request_next_step(response_data['fund_invoice_status'][0]['action_taken'],
                                                      self.context['request'].user.get_user_role_display())
        if response_data['fund_invoice_status'][0]['action_taken'] == settings.CREDIT_REQUEST_ADMIN_APPROVED:
            next_action_data = next_step_based_on_contract_category(
                self.context['request'].user.get_user_role_display(), response_data['contract_category'])
        warning_messages = []
        # if self.context['request'].user.get_user_role_display() == settings.SME["name_value"]:
        #     if next_action_data == "CREDIT_CREATE_SHIPMENT":
        #         warning_messages = get_shipment_warning_message(instance, instance.payment_fund_invoice.filter(
        #             payment_made_by__user_role=settings.ADMIN_ROLE_VALUE,
        #             payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN), instance.supplier_term.supplier_terms.
        #                                                         filter(before_shipment=True))

        # response_data['destination_country_name'] = dict(countries)[response_data['destination_country']]

        # if 'destination_country' in self.context['request'].data:
        #     response_data['destination_country'] = pycountry.countries.get(
        #         alpha_2=response_data['destination_country']).name
        response_data['country_data'] = []
        fund_invoice_country = []
        for data in response_data['fund_invoice_country']:
            if not data['is_deleted']:
                fund_invoice_country.append(data)
                if response_data['shipment_date'] is None:
                    response_data['shipment_date'] = data['shipping_date']
                response_data['country_data'].append({'id': data['origin_city'],
                                                      'name': data['origin_city_name'],
                                                      'display_name': data['origin_display_name'],
                                                      'country': data['origin_country_code']})
                response_data['country_data'].append({'id': data['destination_city'],
                                                      'name': data['destination_city_name'],
                                                      'display_name': data['destination_display_name'],
                                                      'country': data['destination_country_code']})
        response_data['fund_invoice_country'] = fund_invoice_country
        # response_data['shipment_date'] = response_data['fund_invoice_country'][0]['shipping_date']
        response_data['warning_messages'] = warning_messages
        response_data['next_step'] = next_action_data
        if supplier_leads_object.exists():
            response_data['supplier_country_name'] = supplier_leads_object[0].company_registered_in.name
        if instance.contract_fund_invoice.first() is not None:
            response_data["total_sales_amount"] = instance.contract_fund_invoice.first().total_sales_amount
        # Calculating Paid and balance amount.
        response_data['paid_amount'] = calculate_paid_amount(instance)
        if response_data['contract_category'] == models.MASTER_CONTRACT:
            response_data['balance_amount'] = instance.total_sales_amount
        else:
            if instance.contract_fund_invoice.first() is not None:
                response_data['balance_amount'] = instance.contract_fund_invoice.first().total_sales_amount
            else:
                response_data['balance_amount'] = 0
        # if self.context['request'].user.user_role == settings.ADMIN["number_value"]:
        payment_object = models.PaymentModel.objects.filter(payment_type=models.PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                            fund_invoice=instance.id)
        if payment_object.exists():
            response_data['paid_amount'] = (payment_object.aggregate(Sum('paying_amount')).get(
                'paying_amount__sum') or 0)
            if response_data['contract_category'] == models.MASTER_CONTRACT:
                if response_data['paid_amount'] and instance.total_sales_amount and response_data[
                        'paid_amount'] < instance.total_sales_amount:
                    response_data['balance_amount'] = instance.total_sales_amount - response_data['paid_amount']
                else:
                    response_data['balance_amount'] = 0
            else:
                if instance.contract_fund_invoice.first() is not None:
                    response_data['balance_amount'] = instance.contract_fund_invoice.first().total_sales_amount - \
                                                      response_data['paid_amount']
                else:
                    response_data['balance_amount'] = 0
        response_data['repayment_amount'] = response_data['balance_amount']
        return response_data


class SupplierFundInvoiceModelSerializer(serializers.ModelSerializer):
    """
    Serializer class for FundInvoiceModel for supplier view
    """
    sme_company_name = serializers.CharField(source='sme.on_boarding_details.company_name', read_only=True)
    fund_invoice_files = serializers.StringRelatedField(many=True, read_only=True)
    shipment_fund_invoice = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
    transport_mode = ChoiceFieldSerializer(choices=models.TRANSPORT_MODE_CHOICES)
    fund_invoice_country = FundInvoiceCountryModelSerializer(many=True, read_only=True)

    class Meta:
        model = models.FundInvoiceModel
        fields = ['id', 'sme', 'sme_company_name', 'supplier', 'invoice_total_amount', 'fund_invoice_country',
                  'transport_mode', 'currency_used', 'invoice_number', 'invoice_date', 'assign_to', 'shipment_date',
                  'application_status', 'date_created', 'date_modified', 'fund_invoice_files', 'shipment_fund_invoice',
                  'supplier_term']

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        response_data['country_data'] = []
        for data in response_data['fund_invoice_country']:
            response_data['country_data'].append({'id': data['origin_city'],
                                                  'name': data['origin_city_name'],
                                                  'display_name': data['origin_display_name'],
                                                  'country': data['origin_country_code']})
            response_data['country_data'].append({'id': data['destination_city'],
                                                  'name': data['destination_city_name'],
                                                  'display_name': data['destination_display_name'],
                                                  'country': data['destination_country_code']})
        status_object = instance.fund_invoice_status.all()
        response_data['sme_remarks'] = status_object[len(status_object) - 1].remarks
        next_action_data = generate_request_next_step(status_object[0].action_taken,
                                                      self.context['request'].user.get_user_role_display())
        if status_object[0].action_taken == settings.CREDIT_REQUEST_ADMIN_APPROVED:
            next_action_data = next_step_based_on_contract_category(
                self.context['request'].user.get_user_role_display(),
                FundInvoiceModel.objects.get(pk=response_data['id']).contract_category)
        warning_messages = []
        # if next_action_data == "CREDIT_CREATE_SHIPMENT":
        #     warning_messages = get_shipment_warning_message(instance, instance.payment_fund_invoice.filter(
        #         payment_made_by__user_role=settings.ADMIN_ROLE_VALUE, payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN),
        #                                                     instance.supplier_term.supplier_terms.filter(
        #                                                         before_shipment=True))
        response_data['warning_messages'] = warning_messages
        response_data['next_step'] = next_action_data
        return response_data


class PaymentFilesModelSerializers(serializers.ModelSerializer):
    """
    Serializer class for PaymentFilesModel
    """

    class Meta:
        model = models.PaymentFilesModel
        fields = ['payment', 'payment_file']
        extra_kwargs = {'payment': {"write_only": True}}


class PaymentStatusModelSerializer(serializers.ModelSerializer):
    """
    Serializer class for PaymentStatusModel
    """
    action_by_user_name = serializers.CharField(source='action_by.first_name', read_only=True)
    action_taken = ChoiceFieldSerializer(choices=models.PAYMENT_STATUS_ACTION_CHOICES)

    class Meta:
        model = models.PaymentStatusModel
        fields = ['id', 'payment', 'action_by', 'action_by_user_name', 'remarks', 'status_created_date', 'action_taken']
        extra_kwargs = {'payment': {"write_only": True}}


class PaymentModelSerializer(serializers.ModelSerializer):
    """
    Serializers for PaymentModel
    """
    payment_method = ChoiceFieldSerializer(choices=models.PAYMENT_METHOD_CHOICES)
    # payment_status = ChoiceFieldSerializer(choices=models.PAYMENT_STATUS_CHOICES)
    payment_type = ChoiceFieldSerializer(choices=models.PAYMENT_TYPE_CHOICES)
    payment_files = serializers.StringRelatedField(many=True, read_only=True)
    acknowledgement_status = ChoiceFieldSerializer(choices=models.PAYMENT_ACKNOWLEDGMENT_STATUS_CHOICES)

    class Meta:
        model = models.PaymentModel
        fields = ['id', 'fund_invoice', 'paying_amount', 'payment_method', 'tax_amount', 'term_order',
                  'payment_ref_number', 'payment_remarks', 'payment_made_by', 'payment_type', 'acknowledgement_status',
                  'date_modified', 'date_created', 'payment_files', 'acknowledgement_completed', 'is_adhoc',
                  'system_remarks', 'payment_date']
        extra_kwargs = {'system_remarks': {"write_only": True}}

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        next_step = list_payment_next_step(instance, self.context['request'].user.user_role)
        response_data['total_amount'] = float(response_data['paying_amount']) + float(response_data['tax_amount'])
        response_data['next_step'] = next_step
        if response_data['payment_type'] == "PAYMENT_TO_FACTORING_COMPANY_BY_SME":
            del response_data['acknowledgement_status']
        return response_data


class MasterContractStatusSerializers(serializers.ModelSerializer):
    """
    Serializer class for MasterContractStatusModel
    """
    action_by_user_name = serializers.CharField(source='action_by.first_name', read_only=True)

    class Meta:
        model = models.MasterContractStatusModel
        fields = ['id', 'contract', 'action_by', 'action_by_user_name', 'remarks', 'status_created_date',
                  'action_taken', 'assign_to']
        extra_kwargs = {'contract': {"write_only": True}}

    def to_representation(self, instance):
        response_data = super().to_representation(instance)
        if instance.action_by.user_role == settings.SME["number_value"]:
            user_role = "SME"
        elif instance.action_by.user_role == settings.ADMIN["number_value"]:
            user_role = "ADMIN"
        next_step = generate_request_next_step(instance.action_taken,
                                               user_role, True)
        response_data['next_step'] = next_step
        return response_data


class AccountDetailsModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AccountDetailsModel
    """

    class Meta:
        model = models.AccountDetailsModel
        fields = '__all__'


class CitySerializer(serializers.ModelSerializer):
    """
    Serializer for Country Model
    """
    country = serializers.CharField(source='country.code2', read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'display_name', 'country']


class ContractAdditionalCostTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractAdditionalCostType model
    """

    class Meta:
        model = models.ContractAdditionalCostType
        fields = '__all__'


class NotificationModelSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationModel
    """
    lead_first_name = serializers.CharField(source='lead_user.first_name', read_only=True)
    lead_last_name = serializers.CharField(source='lead_user.last_name', read_only=True)
    lead_company_name = serializers.CharField(source='lead_user.company_name', read_only=True)
    lead_invoice_amount = serializers.CharField(source='lead_user.invoice_amount', read_only=True)
    fund_invoice_sme = serializers.CharField(source='fund_invoice.sme.first_name', read_only=True)
    fund_invoice_sme_company_name = serializers.CharField(source='fund_invoice.sme.on_boarding_details.company_name', read_only=True)
    fund_invoice_total_amount = serializers.CharField(source='fund_invoice.invoice_total_amount', read_only=True)
    fund_invoice_supplier = serializers.CharField(source='fund_invoice.supplier.first_name', read_only=True)
    fund_invoice_supplier_company_name = serializers.CharField(source='fund_invoice.supplier.on_boarding_details.company_name', read_only=True)
    user_first_name = serializers.CharField(source='user.first_name', read_only=True)
    user_last_name = serializers.CharField(source='user.last_name', read_only=True)
    user_company_name = serializers.CharField(source='user.on_boarding_details.company_name', read_only=True)
    user_credit_limit = serializers.CharField(source='user.credit_limit', read_only=True)
    shipment_supplier = serializers.CharField(source='shipment.fund_invoice.supplier.first_name', read_only=True)
    shipment_sme = serializers.CharField(source='shipment.fund_invoice.sme.first_name', read_only=True)
    shipment_sme_company_name =\
        serializers.CharField(source='shipment.fund_invoice.sme.on_boarding_details.company_name', read_only=True)
    shipment_supplier_company_name = serializers.CharField(source='shipment.fund_invoice.supplier.on_boarding_details.company_name', read_only=True)
    shipment_fund_invoice = serializers.CharField(source='shipment.fund_invoice', read_only=True)
    contract_fund_invoice = serializers.CharField(source='contract.fund_invoice', read_only=True)
    contract_number = serializers.CharField(source='contract.contract_number', read_only=True)


    class Meta:
        model = models.NotificationModel
        fields = '__all__'

    def to_representation(self, instance):
        response_data = super().to_representation(instance)

        if instance.user_id is not None:
            response_user = User.objects.get(id=instance.user_id)
            if response_user.user_role == 2:
                response_data['user_role'] = 'SME'
            elif response_user.user_role == 3:
                response_data['user_role'] = 'SUPPLIER'
            elif response_user.user_role == 4:
                response_data['user_role'] = 'FACTOR'
        response_data['date'] = calendar.day_name[instance.date.weekday()] + ", " + \
                                calendar.month_name[instance.date.month][:3] + " " + \
                                str(instance.date.day)

        if instance.contract is not None:
            if instance.contract.is_master_contract is False:
                response_data['fund_invoice_files'] = FundInvoiceModelSerializer(instance.contract.fund_invoice,
                                                                                 context={'request': self.context[
                                                                                     'request']}).data[
                    'fund_invoice_files']
            response_data['is_master_contract'] = instance.contract.is_master_contract
        if instance.fund_invoice is not None:
            fund_invoice_status = FundInvoiceStatusModelSerializer(instance.fund_invoice.
                                                                   fund_invoice_status, many=True).data
            if fund_invoice_status[0]['action_taken'] == settings.CREDIT_REQUEST_ADMIN_APPROVED:
                next_action_data = next_step_based_on_contract_category(
                    self.context['request'].user.get_user_role_display(), instance.fund_invoice.contract_category)
                warning_messages = []

                # if self.context['request'].user.get_user_role_display() == settings.SME["name_value"]:
                #     if next_action_data == "CREDIT_CREATE_SHIPMENT":
                #         warning_messages = get_shipment_warning_message(instance.fund_invoice, instance.fund_invoice.payment_fund_invoice.filter(
                #             payment_made_by__user_role=settings.ADMIN_ROLE_VALUE,
                #             payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN), instance.fund_invoice.supplier_term.supplier_terms.
                #                                                         filter(before_shipment=True))
                response_data['warning_messages'] = warning_messages

        return response_data

    # class SMERemainderSerializers(serializers.ModelSerializer):
#     """
#     Serializer class for MasterContractStatusModel
#     """
#     class Meta:
#         model = models.SigningRemainderModel
#         fields = ['contract','sending_time','count']

# old code
# class SupportingDocsModelSerializers(serializers.ModelSerializer):
#     """
#     Serializer class for SupportingDocsModel
#     """
#
#     class Meta:
#         model = models.SupportingDocsModel
#         fields = ['request', 'supporting_doc', 'file_path']
#         extra_kwargs = {'request': {"write_only": True}, 'file_path': {"write_only": True}}
#
#
# class RequestStatusModelSerializer(serializers.ModelSerializer):
#     """
#     Serializer class for RequestStatusModel
#     """
#     action_by_user_name = serializers.CharField(source='action_by.first_name', read_only=True)
#
#     class Meta:
#         model = models.RequestStatusModel
#         fields = ['request', 'action_by', 'action_by_user_name', 'status_stage', 'remarks',
#                   'status_created_date', 'status']
#         extra_kwargs = {'request': {"write_only": True}}
#
#
# class InvoiceFilesModelSerializers(serializers.ModelSerializer):
#     """
#     Serializer class for InvoiceFilesModel
#     """
#
#     class Meta:
#         model = models.InvoiceFilesModel
#         fields = ['invoice', 'invoice_file', 'invoice_file_path']
#         extra_kwargs = {'invoice': {"read_only": True}, 'invoice_file_path': {"read_only": True}}
#
#
# class RequestInvoiceModelSerializer(serializers.ModelSerializer):
#     """
#     Serializer class for RequestInvoiceModel
#     """
#     invoice_files = serializers.StringRelatedField(many=True, read_only=True)
#     supplier_company_name = serializers.CharField(source='request.supplier.on_boarding_details.company_name',
#                                                   read_only=True)
#     supplier_company_id = serializers.CharField(source='request.supplier.id', read_only=True)
#     sme_company_name = serializers.CharField(source='request.sme.on_boarding_details.company_name', read_only=True)
#     contract_invoice = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
#
#     class Meta:
#         model = models.RequestInvoiceModel
#         fields = ['id', 'request', 'invoice_number', 'invoice_date', 'shipment_date', 'total_amount', 'total_vat',
#                   'grand_total', 'invoice_status', 'supplier_company_name', 'supplier_company_id', 'sme_company_name',
#                   'invoice_files', 'contract_invoice']
#
#     def to_representation(self, instance):
#         response_data = super().to_representation(instance)
#         response_status = RequestStatusModel.objects.filter(request=response_data["request"]).order_by("-id")[0]
#         next_step = list_invoice_next_step(response_status.status, self.context['request'].user.get_user_role_display())
#         response_data['invoice_approval_status'] = float(instance.grand_total) <= float(instance.request.credit_amount)
#         response_data['next_step'] = next_step
#         return response_data
#
#
# class RequestModelSerializer(serializers.ModelSerializer):
#     """
#     Serializer class for RequestModel
#     """
#     supplier_company_name = serializers.CharField(source='supplier.on_boarding_details.company_name', read_only=True)
#     sme_company_name = serializers.CharField(source='sme.on_boarding_details.company_name', read_only=True)
#     request_supporting_docs = serializers.StringRelatedField(many=True, read_only=True)
#     request_status = RequestStatusModelSerializer(many=True, read_only=True)
#     request_invoice = RequestInvoiceModelSerializer(many=True, read_only=True)
#
#     class Meta:
#         model = models.RequestModel
#         fields = ['id', 'sme', 'sme_company_name', 'supplier', 'supplier_company_name', 'credit_amount',
#                   'currency_used', 'purpose', 'status_stage', 'assign_to', 'status_stage_completed', 'applied_date',
#                   'rejected_status', 'request_supporting_docs', 'request_status', 'request_invoice']
#
#     def to_representation(self, instance):
#         response_data = super().to_representation(instance)
#         # response_data['credit_amount'] = convert_currency_value(response_data['currency_stored'],
#         #                                                         response_data['currency_used'],
#         #                                                         response_data['credit_amount'])
#         next_action_data = generate_request_next_step(response_data['status_stage'],
#                                                       response_data['status_stage_completed'],
#                                                       response_data['assign_to'],
#                                                       self.context['request'].user.get_user_role_display(),
#                                                       response_data['request_status'][0]['status'])
#         response_data['next_step'] = next_action_data
#         return response_data
#
#
# class SupplierRequestModelSerializer(serializers.ModelSerializer):
#     """
#     Serializer class for RequestModel
#     """
#     supplier_company_name = serializers.CharField(source='supplier.on_boarding_details.company_name', read_only=True)
#     sme_company_name = serializers.CharField(source='sme.on_boarding_details.company_name', read_only=True)
#     request_invoice = RequestInvoiceModelSerializer(many=True, read_only=True)
#
#     class Meta:
#         model = models.RequestModel
#         fields = ['id', 'sme', 'sme_company_name', 'supplier', 'supplier_company_name', 'request_invoice']
#
#     def to_representation(self, instance):
#         response_data = super().to_representation(instance)
#         status_object = instance.request_status.filter(request=response_data['id'],
#                                                        status=settings.CREDIT_INVOICE_REQUEST_SUPPLIER)
#         if status_object.exists():
#             response_data['sme_remarks'] = status_object[0].remarks
#             response_data['upload_request_date'] = status_object[0].status_created_date
#         else:
#             response_data['sme_remarks'] = None
#             response_data['upload_request_date'] = None
#         response_data['next_step'] = generate_request_next_step(instance.status_stage,
#                                                                 instance.status_stage_completed, instance.assign_to,
#                                                                 self.context['request'].user.get_user_role_display())
#         return response_data
