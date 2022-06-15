import json
from datetime import datetime
from django.http import response
import django_filters
import os
import pdfkit
from django.db.models import Q
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework import viewsets, status, filters, pagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.contrib.auth import get_user_model
from registration.permissions import IsCustomAdminUser
import pycountry
from . import models
from . import serializers
from contact_app import models as contact_app_models
from cities_light.models import City
from utils.utility import get_user_available_amount, generate_request_status, generate_request_next_step, \
    check_sme_terms_valid, calculate_total_sales_amount, get_payment_balance_amount, check_contract_type_valid, \
    docu_sign_make_envelope, get_docu_sign_doc, check_supplier_terms_valid, get_payment_warning_message, \
    payment_to_supplier_details, payment_to_admin_details, payment_to_factor_details, get_shipment_warning_message, \
    shipment_send_back_email, sme_reminder_mail, payment_acknowledgment_mail, payment_acknowledgment_mail_sme, \
    get_new_contract_number, calculate_total_cogs_value, calculate_total_cogs_amount_for_admin, \
    calculate_total_sales_amount_for_admin, calculate_overdue_amount
from .serializers import AccountDetailsModelSerializer

User = get_user_model()


class FundInvoiceViewSet(viewsets.ModelViewSet):
    """
    Class for Create, List, and Retrieve operations on FundInvoiceModel
    """
    queryset = models.FundInvoiceModel.objects.all()
    serializer_class = serializers.FundInvoiceModelSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    http_method_names = ['get', 'post']

    def create(self, request, *args, **kwargs):
        if request.user.is_user_onboard and request.user.user_role == settings.SME['number_value']:

            if 'invoice_files' not in request.FILES:
                return Response({
                    "detail": "Invoice file is needed for creating a new fund invoice request"},
                    status=status.HTTP_400_BAD_REQUEST)
            if 'invoice_total_amount' not in request.POST:
                return Response({"invoice_total_amount": ["This field is required."]},
                                status=status.HTTP_400_BAD_REQUEST)
            if 'contract_category' in request.POST:
                return Response({"contract_category": "You dont have permission to add this field."},
                                status=status.HTTP_400_BAD_REQUEST)
            if 'country_data' not in request.POST:
                return Response({"country_data": "This field is required."},
                                status=status.HTTP_400_BAD_REQUEST)
            if float(request.POST['invoice_total_amount']) <= 0:
                return Response({
                    "detail": "Invoice total amount should be greater than 0"},
                    status=status.HTTP_400_BAD_REQUEST)
            if request.POST.get('transport_mode') == str(models.TRANSPORT_MODE_MIXED) and \
                    len(eval(str(request.POST['country_data']).replace('null', 'None'))) < 2:
                return Response({
                    "detail": "Need two or more shipping details"},
                    status=status.HTTP_400_BAD_REQUEST)

            if request.user.master_contract is None:
                return Response({"detail": "Please create a master contract for this sme"},
                                status=status.HTTP_400_BAD_REQUEST)
            else:
                if models.MasterContractStatusModel.objects.filter(contract=request.user.master_contract). \
                        first().action_taken == \
                        settings.CREDIT_CONTRACT_SME_APPROVED:
                    pass
                else:
                    return Response({"detail": "Please complete the master contract signing process"},
                                    status=status.HTTP_400_BAD_REQUEST)
            available_amount = get_user_available_amount(request.user.id)
            # converted_amount = convert_currency_value(request.POST['currency_used'], request.user.currency_value,
            #                                           request.POST["credit_amount"])
            # if float(converted_amount) <= available_amount:
            if float(request.POST["invoice_total_amount"]) <= available_amount:
                # Entering the request data to RequestModel Table
                input_dict = request.POST.copy()
                if "supplier" in request.POST:
                    input_dict["sme"] = request.user.id
                    other_user_id = input_dict["supplier"]
                else:
                    return Response({
                        "supplier": [
                            "This field is required."
                        ]
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Checking if the other user (Supplier) has completed the on boarding process
                try:
                    User.objects.get(id=other_user_id, is_user_onboard=True, user_role=3, is_active=True)
                except:
                    user_object = User.objects.get(id=other_user_id)
                    leads_object = contact_app_models.LeadsModel.objects.get(sign_up_email=user_object.email)
                    if leads_object.created_by != request.user:
                        return Response({'detail': 'Sorry you cannot add this supplier for funding invoice'},
                                        status=status.HTTP_400_BAD_REQUEST)
                status_data = generate_request_status(settings.CREDIT_REQUEST_CREATED)
                input_dict["assign_to"] = status_data[1]
                # input_dict["currency_stored"] = request.user.currency_value
                # input_dict["credit_amount"] = converted_amount
                if 'supplier_term' in request.data:
                    try:
                        models.PaymentTermModel.objects.get(id=request.data['supplier_term'],
                                                            for_sme=False)
                    except models.PaymentTermModel.DoesNotExist:
                        return Response(
                            {'detail': 'Sorry you cannot add this supplier term.'},
                            status=status.HTTP_400_BAD_REQUEST)
                    input_dict['supplier_term'] = request.data['supplier_term']
                country_data = json.loads((input_dict['country_data']))
                input_dict['shipment_date'] = country_data[0]['shipping_date']
                input_dict['fixed_fee_value'] = request.user.master_contract.contract_type.fixed_fee_value
                fund_invoice_serializer_data = self.serializer_class(data=input_dict, context={"request": request})
                fund_invoice_serializer_data.is_valid(raise_exception=True)
                fund_invoice_data = fund_invoice_serializer_data.save()

                # Entering the request data status to FundInvoiceStatusModel Table
                fund_invoice_status_data = {"fund_invoice": fund_invoice_data.id, "action_taken": status_data[0],
                                            'action_by': request.user.id}
                if "supplier_ref_remarks" in input_dict:
                    fund_invoice_status_data['remarks'] = input_dict["supplier_ref_remarks"]
                status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()

                # Entering the request invoice files to FundInvoiceFilesModel Table
                invoice_files_list = list()
                for file_object in request.FILES.getlist('invoice_files'):
                    invoice_files_list.append(models.FundInvoiceFilesModel(fund_invoice=fund_invoice_data,
                                                                           file_object=file_object))
                if 'other_document' in request.FILES:
                    invoice_files_list.append(models.FundInvoiceFilesModel(fund_invoice=fund_invoice_data,
                                                                           file_object=request.FILES['other_document']))
                models.FundInvoiceFilesModel.objects.bulk_create(invoice_files_list)

                # Entering the request shipping data in FundInvoiceCountryModel
                if 'country_data' in input_dict:
                    country_serializer_data = serializers.FundInvoiceCountryModelSerializer(
                        data=eval(str(input_dict['country_data']).replace('null', 'None')), many=True,
                        context={'fund_invoice': fund_invoice_data})
                    country_serializer_data.is_valid(raise_exception=True)
                    country_serializer_data.save()
                notification_data = {"fund_invoice": fund_invoice_data.id,
                                     "notification": "A Fund Request was Added",
                                     "type": settings.FUND_REQUEST_ADDED,
                                     "description": "Fund Request Approval is Pending",
                                     }
                notification_serializer = serializers.NotificationModelSerializer(data=notification_data)

                if notification_serializer.is_valid(raise_exception=True):
                    notification_serializer.save()
                return Response({'message': 'Fund invoice request added successfully!',
                                 'data': fund_invoice_serializer_data.data}, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'detail': 'Applied invoice total is more than available amount!'},
                    status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def retrieve(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = self.get_queryset().filter(is_deleted=False)
            invoice_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(invoice_object, context={"request": request})
            output_dict = serializer_data.data
            output_dict['sme_credit_limit'] = invoice_object.sme.credit_limit
            output_dict['sme_master_contract'] = invoice_object.sme.master_contract.id
            output_dict['contract_type'] = invoice_object.sme.master_contract.contract_type.id
            output_dict['invoice_grand_total'] = invoice_object.invoice_total_amount

            # if not  invoice_object.is_deleted:
            output_dict['sme_available_amount'] = get_user_available_amount(output_dict['sme'])
            output_dict['supplier_terms'] = serializers.PaymentTermModelSerializer(invoice_object.supplier_term).data
            if invoice_object.contract_category == settings.NEW_CONTRACT["number_value"]:
                output_dict['view_payment'] = invoice_object.fund_invoice_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
                if invoice_object.contract_fund_invoice.first() is not None:
                    output_dict["total_sales_amount"] = invoice_object.contract_fund_invoice.first().total_sales_amount
            elif invoice_object.contract_category == settings.MASTER_CONTRACT["number_value"]:
                output_dict['view_payment'] = invoice_object.sme.master_contract.master_contract_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
                output_dict['sme_payment_terms'] = serializers.PaymentTermModelSerializer(
                    invoice_object.sme.master_contract.
                    contract_type.payment_terms, context={"fund_invoice_id": invoice_object.id}).data
            else:
                output_dict['view_payment'] = False
            return Response({'data': output_dict}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.SME["number_value"]:
            queryset_filter = self.get_queryset().filter(sme=request.user, is_deleted=False)
            request_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            output_dict = (self.serializer_class(request_data_object, context={"request": request})).data
            output_dict['supplier_terms'] = serializers.PaymentTermModelSerializer(request_data_object.supplier_term). \
                data
            if request_data_object.contract_category == settings.NEW_CONTRACT["number_value"]:
                output_dict["view_payment"] = request_data_object.fund_invoice_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
                if request_data_object.contract_fund_invoice.first() is not None:
                    output_dict[
                        "total_sales_amount"] = request_data_object.contract_fund_invoice.first().total_sales_amount
            elif request_data_object.contract_category == settings.MASTER_CONTRACT["number_value"]:
                output_dict[
                    'view_payment'] = request_data_object.sme.master_contract.master_contract_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
                output_dict['sme_payment_terms'] = serializers.PaymentTermModelSerializer(
                    request_data_object.sme.master_contract.
                    contract_type.payment_terms, context={"fund_invoice_id": request_data_object.id}).data
            else:
                output_dict['view_payment'] = False
            output_dict['sme_master_contract'] = request_data_object.sme.master_contract.id
            output_dict['contract_type'] = request_data_object.sme.master_contract.contract_type.id
            output_dict['invoice_grand_total'] = request_data_object.invoice_total_amount

            # if output_dict['destination_country'] is not None:
            #     output_dict['destination_country'] = mapping.get(output_dict['destination_country'])
            return Response({'data': output_dict}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.SUPPLIER["number_value"]:
            queryset_filter = self.get_queryset().filter(supplier=request.user, is_deleted=False)
            request_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            output_dict = (serializers.SupplierFundInvoiceModelSerializer(request_data_object,
                                                                          context={"request": request})).data
            output_dict['supplier_terms'] = serializers.PaymentTermModelSerializer(request_data_object.supplier_term). \
                data
            output_dict["view_payment"] = request_data_object.fund_invoice_status.all().filter(
                action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
            return Response({'data': output_dict}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            queryset_filter = self.get_queryset().filter(Q(contract_fund_invoice__factoring_company=request.user) |
                                                         Q(factoring_company=request.user),
                                                         is_deleted=False)
            invoice_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(invoice_object, context={"request": request})
            output_dict = serializer_data.data
            output_dict['sme_credit_limit'] = invoice_object.sme.credit_limit
            output_dict['sme_available_amount'] = get_user_available_amount(output_dict['sme'])
            output_dict['supplier_terms'] = serializers.PaymentTermModelSerializer(invoice_object.supplier_term). \
                data
            output_dict["view_payment"] = invoice_object.fund_invoice_status.all().filter(
                action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
            mapping = {country.name: country.alpha_2 for country in pycountry.countries}
            if output_dict['destination_country'] is not None:
                output_dict['destination_country'] = mapping.get(output_dict['destination_country'])
            return Response({'data': output_dict}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def list(self, request, *args, **kwargs):
        if 'from_date' in request.GET:
            from_date = request.GET['from_date']
        else:
            from_date = None
        if 'to_date' in request.GET:
            to_date = request.GET['to_date']
        else:
            to_date = None
        if request.user.user_role == settings.ADMIN["number_value"]:
            queryset_data = self.get_queryset().filter(is_deleted=False)
            if to_date and from_date:
                queryset_data = queryset_data.filter(date_created__gte=from_date, date_created__lte=to_date)
            if request.GET.get("next_action") == "under_production":
                queryset_data = queryset_data.filter(
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED) |
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED)
                    , is_deleted=False)
            if request.GET.get("next_action") == "pending_submission":
                queryset_data = queryset_data.filter(
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_CREATED) |
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_CREATED),
                    is_deleted=False).exclude(
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED) |
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED)
                )
            sme = self.request.query_params.get('sme_id')
            if sme:
                queryset_data = queryset_data.filter(sme=sme, is_deleted=False,
                                                     fund_invoice_status__action_taken__contains=
                                                     settings.CREDIT_REQUEST_ADMIN_APPROVED).exclude(Q(
                    fund_invoice_status__action_taken__contains=
                    settings.CREDIT_CONTRACT_ADMIN_CREATED) | Q(
                    contract_category=settings.MASTER_CONTRACT["number_value"]))
            page = self.paginate_queryset(queryset_data)
            if page is not None:
                total_cogs_value = calculate_total_cogs_amount_for_admin()
                total_sales_amount = calculate_total_sales_amount_for_admin()
                serializer = self.serializer_class(page, many=True, context={"request": request})
                paginated_response = self.get_paginated_response(serializer.data)
                paginated_response.data["sme_invoice_total_amount"] = total_cogs_value["invoice_total_amount__sum"]
                paginated_response.data["total_sales_amount"] = total_sales_amount
                return paginated_response
        elif request.user.user_role == settings.SUPPLIER["number_value"]:
            if from_date and to_date is not None:
                page = self.paginate_queryset((self.get_queryset().filter(supplier=request.user, is_deleted=False,
                                                                          date_created__lte=to_date,
                                                                          date_created__gte=from_date)))
            else:
                page = self.paginate_queryset((self.get_queryset().filter(supplier=request.user, is_deleted=False)))
            if page is not None:
                serializer = serializers.SupplierFundInvoiceModelSerializer(page, many=True,
                                                                            context={"request": request})
                return self.get_paginated_response(serializer.data)
        elif request.user.user_role == settings.SME["number_value"]:
            total_cogs_value = calculate_total_cogs_value(request.user.id)
            if from_date and to_date is not None:
                page = self.paginate_queryset(self.get_queryset().filter(sme=request.user, is_deleted=False,
                                                                         date_created__lte=to_date,
                                                                         date_created__gte=from_date))
            else:
                page = self.paginate_queryset(self.get_queryset().filter(sme=request.user, is_deleted=False))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                paginated_response = self.get_paginated_response(serializer.data)
                paginated_response.data["sme_invoice_total_amount"] = total_cogs_value["invoice_total_amount__sum"]
                return paginated_response
        elif request.user.user_role == settings.FACTOR["number_value"]:
            if from_date and to_date is not None:
                page = self.paginate_queryset(
                    self.get_queryset().filter(Q(contract_fund_invoice__factoring_company=request.user) |
                                               (Q(factoring_company=request.user)),
                                               is_deleted=False, date_created__lte=to_date,
                                               date_created__gte=from_date))
            else:
                page = self.paginate_queryset(
                    self.get_queryset().filter(Q(contract_fund_invoice__factoring_company=request.user) |
                                               (Q(factoring_company=request.user)),
                                               is_deleted=False))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class RequestAdminApprovalView(APIView):
    """
    Class for approving/rejecting a fund invoice request made by User (permission only for admins)
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request, **kwargs):
        if kwargs['admin_action'] == settings.CREDIT_REQUEST_APPROVED:
            if 'contract_category' not in request.data:
                return Response({'details': 'Please add contract_category.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                if str(request.data["contract_category"]) == str(settings.MASTER_CONTRACT["number_value"]):
                    keys = ['total_sales_amount', 'fixed_fee_value']
                    for key in keys:
                        if key not in request.data:
                            return Response({'details': key + ' is required.'}, status=status.HTTP_400_BAD_REQUEST)
                    factoring_company = ''
                    if 'factoring_company' in request.data:
                        if request.data['factoring_company'] != 'none':
                            try:
                                factoring_company = User.objects.get(id=request.data['factoring_company'],
                                                                     is_user_onboard=True,
                                                                     user_role=settings.FACTOR["number_value"],
                                                                     is_active=True)

                            except User.DoesNotExist:
                                return Response(
                                    {'detail': 'Sorry you cannot add this factoring company for creating a contract'},
                                    status=status.HTTP_400_BAD_REQUEST)
                status_data = generate_request_status(settings.CREDIT_REQUEST_ADMIN_APPROVED)
                fund_invoice_status = models.FUND_INVOICE_APPROVED
                response_message = {'message': 'Fund invoice request approved'}
                try:
                    supplier_term_object = models.PaymentTermModel.objects.get(for_sme=False,
                                                                               id=request.data["supplier_term_id"],
                                                                               is_delete=False)
                except:
                    return Response({'detail': 'Please check/add the supplier payment term'},
                                    status=status.HTTP_400_BAD_REQUEST)

        elif kwargs['admin_action'] == settings.CREDIT_REQUEST_REJECTED:
            status_data = generate_request_status(settings.CREDIT_REQUEST_ADMIN_REJECTED)
            fund_invoice_status = models.FUND_INVOICE_REJECTED
            response_message = {'message': 'Fund invoice request rejected'}
        else:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Checking if the other user (Supplier) has completed the on boarding process
        # try:
        #     supplier_term_object = models.PaymentTermModel.objects.get(for_sme=False,
        #                                                                id=request.data["supplier_term_id"])
        # except:
        #     return Response({'detail': 'Please check/add the supplier payment term'},
        #                     status=status.HTTP_400_BAD_REQUEST)

        # Updating FundInvoiceModel
        queryset_filter = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                 settings.CREDIT_REQUEST_CREATED).exclude(
            fund_invoice_status__action_taken__contains=
            settings.CREDIT_REQUEST_ADMIN_APPROVED)
        fund_invoice_object = get_object_or_404(queryset_filter, pk=kwargs['fund_invoice_id'], is_deleted=False)
        fund_invoice_object.assign_to = status_data[1]
        fund_invoice_object.application_status = fund_invoice_status
        if kwargs['admin_action'] == settings.CREDIT_REQUEST_APPROVED:
            fund_invoice_object.supplier_term = supplier_term_object
            fund_invoice_object.contract_category = request.data['contract_category']
            if str(fund_invoice_object.contract_category) == str(settings.MASTER_CONTRACT["number_value"]):
                fund_invoice_object.total_sales_amount = request.data['total_sales_amount']
                fund_invoice_object.fixed_fee_value = request.data['fixed_fee_value']
                if float(request.data.get('gross_margin', 0)) > 100:
                    return Response({'gross_margin': 'Should be bellow 100'}, status=status.HTTP_400_BAD_REQUEST)
                if float(request.data.get('markup', 0)) > 100:
                    return Response({'markup': 'Should be bellow 100'}, status=status.HTTP_400_BAD_REQUEST)
                fund_invoice_object.gross_margin = request.data.get('gross_margin')
                fund_invoice_object.markup = request.data.get('markup')
                fund_invoice_object.date_approved = datetime.now()
                if factoring_company is not "":
                    fund_invoice_object.factoring_company = factoring_company
                notification_data = {"fund_invoice": fund_invoice_object.id,
                                     "notification": "Fund Request was Approved",
                                     "type": settings.FUND_REQUEST_APPROVED,
                                     "description": "Shipment Upload is Pending",
                                     "assignee": fund_invoice_object.sme.id
                                     }
                notification_serializer = serializers.NotificationModelSerializer(data=notification_data)
                if notification_serializer.is_valid(raise_exception=True):
                    notification_serializer.save()
        fund_invoice_object.save()

        # Entering the request data status to FundInvoiceStatusModel Table
        fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                    'action_by': request.user.id}
        if "remarks" in request.data:
            fund_invoice_status_data['remarks'] = request.data["remarks"]
        status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
        status_serializer_data.is_valid(raise_exception=True)
        status_serializer_data.save()
        notification_obj = models.NotificationModel.objects.filter(fund_invoice_id=fund_invoice_object.id,
                                                                   type=settings.FUND_REQUEST_ADDED)
        if notification_obj.exists():
            notification_obj.update(is_completed=True)

        return Response(response_message, status=status.HTTP_200_OK)


class PaymentTermsViewSet(viewsets.ModelViewSet):
    """
    Class for CRUD operations Payment Terms data
    """
    queryset = models.PaymentTermModel.objects.all()
    serializer_class = serializers.PaymentTermModelSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'put']
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['for_sme']

    def create(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN['number_value']:
            if request.data['for_sme']:
                # Checking if sme terms added is valid
                if 'is_installment' in request.data:
                    terms_status = check_sme_terms_valid(request.data['terms'], request.data['is_installment'])
                    if not terms_status[0]:
                        return Response({"detail": terms_status[2]}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({"detail": "Please add the type of terms added"},
                                    status=status.HTTP_400_BAD_REQUEST)
            else:
                # Checking if supplier terms added is valid
                terms_status = check_supplier_terms_valid(request.data['terms'])
                if not terms_status[0]:
                    return Response({"detail": terms_status[2]}, status=status.HTTP_400_BAD_REQUEST)

            payment_serializer_data = self.serializer_class(data=request.data)
            payment_serializer_data.is_valid(raise_exception=True)
            payment_terms_object = payment_serializer_data.save()

            if request.data['for_sme']:
                if not request.data['is_installment']:
                    for terms in request.data['terms']:
                        if terms['type'] == models.TERMS_TYPE_BALANCE:
                            terms['value'] = terms_status[1]
                            terms['type'] = terms_status[3]
                        terms['payment_term'] = payment_terms_object.id
                        terms_serializer_data = serializers.SmeTermsAmountModelSerializer(data=terms)
                        terms_serializer_data.is_valid(raise_exception=True)
                        terms_serializer_data.save()
                else:
                    term_dict = request.data['terms']
                    term_dict['payment_term'] = payment_terms_object.id
                    terms_serializer_data = serializers.SmeTermsInstallmentModelSerializer(data=term_dict)
                    terms_serializer_data.is_valid(raise_exception=True)
                    terms_serializer_data.save()
            else:
                for terms in request.data['terms']:
                    if terms['value_type'] == models.TERMS_TYPE_BALANCE:
                        terms['value'] = terms_status[1]
                        terms['value_type'] = terms_status[3]
                    terms['payment_term'] = payment_terms_object.id
                    terms_serializer_data = serializers.SupplierTermsModelSerializer(data=terms)
                    terms_serializer_data.is_valid(raise_exception=True)
                    terms_serializer_data.save()
            return Response({'message': 'Payment term created successfully!', 'data': payment_serializer_data.data},
                            status=status.HTTP_201_CREATED)
        else:
            return Response({'detail': 'you dont have permission to perform this action.'},
                            status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN['number_value']:
            payment_term = get_object_or_404(models.PaymentTermModel, pk=kwargs['pk'], is_delete=False)
            if payment_term.for_sme is False:
                if payment_term.invoice_supplier_terms.all().count() == 0:
                    payment_term_serializer = self.serializer_class(payment_term, data=request.data)
                    payment_term_serializer.is_valid(raise_exception=True)
                    payment_term_serializer.save()
                    for terms in request.data['terms']:
                        term_obj = models.SupplierTermsModel.objects.get(pk=terms['id'])
                        terms['payment_term'] = payment_term.id
                        terms_serializer_data = serializers.SupplierTermsModelSerializer(term_obj, data=terms)
                        terms_serializer_data.is_valid(raise_exception=True)
                        terms_serializer_data.save()
                    return Response(
                        {'message': 'Supplier Payment term Updated successfully!',
                         'data': payment_term_serializer.data},
                        status=status.HTTP_200_OK)
                else:
                    update_dict = dict()
                    editable_fields = ['name', 'description']
                    for field in editable_fields:
                        if field in request.data and request.data[field] is not None:
                            update_dict[field] = request.data[field]
                    payment_term_serializer = self.serializer_class(payment_term, data=update_dict, partial=True)
                    payment_term_serializer.is_valid(raise_exception=True)
                    self.perform_update(payment_term_serializer)
                    return Response(
                        {'message': 'Supplier Payment term Updated successfully!',
                         'data': payment_term_serializer.data},
                        status=status.HTTP_200_OK)
            elif payment_term.for_sme:
                if payment_term.payment_terms.all().count() == 0:
                    payment_term_serializer_sme = self.serializer_class(payment_term, data=request.data)
                    payment_term_serializer_sme.is_valid(raise_exception=True)
                    payment_term_serializer_sme.save()
                    if not request.data['is_installment']:
                        if 'terms' in request.data:
                            for sme_term in request.data['terms']:
                                sme_term_object = models.SmeTermsAmountModel.objects.get(id=sme_term['id'])
                                sme_term['payment_term'] = payment_term.id
                                sme_term_serializer = serializers.SmeTermsAmountModelSerializer(sme_term_object,
                                                                                                data=sme_term)
                                sme_term_serializer.is_valid(raise_exception=True)
                                sme_term_serializer.save()
                    else:
                        term_dict = request.data['terms']
                        sme_term_installment_object = models.SmeTermsInstallmentModel.objects.get(id=term_dict['id'])
                        term_dict['payment_term'] = payment_term.id
                        terms_serializer_data = serializers.SmeTermsInstallmentModelSerializer(
                            sme_term_installment_object,
                            data=term_dict)
                        terms_serializer_data.is_valid(raise_exception=True)
                        terms_serializer_data.save()
                    return Response(
                        {'message': 'SME Payment term Updated successfully!', 'data': payment_term_serializer_sme.data},
                        status=status.HTTP_200_OK)
                else:
                    update_dict = dict()
                    editable_fields = ['name', 'description']
                    for field in editable_fields:
                        if field in request.data and request.data[field] is not None:
                            update_dict[field] = request.data[field]
                    payment_term_serializer = self.serializer_class(payment_term, data=update_dict, partial=True)
                    payment_term_serializer.is_valid(raise_exception=True)
                    self.perform_update(payment_term_serializer)
                    return Response(
                        {'message': 'SME Payment term Updated successfully!', 'data': payment_term_serializer.data},
                        status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'you dont have permission to perform this action.'},
                            status=status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        for_sme = self.request.query_params.get('for_sme')
        if request.user.user_role == settings.ADMIN['number_value']:
            if for_sme == "1":
                page = self.paginate_queryset(self.get_queryset().filter(for_sme=True, is_delete=False))
            else:
                page = self.paginate_queryset(self.get_queryset().filter(for_sme=False, is_delete=False))
        elif request.user.user_role == settings.SME['number_value']:
            if for_sme == "1":
                return Response({'detail': 'you dont have permission to perform this action.'},
                                status=status.HTTP_400_BAD_REQUEST)
            else:
                page = self.paginate_queryset(self.get_queryset().filter(for_sme=False, is_delete=False))
        else:
            return Response({'detail': 'you dont have permission to perform this action.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if page is not None:
            serializer = self.serializer_class(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            term_object = get_object_or_404(self.queryset, pk=kwargs['pk'], is_delete=False)
        elif request.user.user_role == settings.SME["number_value"]:
            term_object = get_object_or_404(self.queryset, for_sme=False, pk=kwargs['pk'], is_delete=False)
        else:
            return Response({'detail': 'you dont have permission to perform this action.'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializers_data = self.serializer_class(term_object)
        return Response({'data': serializers_data.data}, status=status.HTTP_200_OK)


class ContractTypeViewSet(viewsets.ModelViewSet):
    """
    Class for CRUD operations Contract Type data
    """
    queryset = models.ContractTypeModel.objects.all()
    serializer_class = serializers.ContractTypeModelSerializer
    permission_classes = [IsCustomAdminUser]
    http_method_names = ['get', 'post', 'put', 'delete']

    def create(self, request, *args, **kwargs):
        contract_type_status = check_contract_type_valid(request.data)
        if not contract_type_status[0]:
            return Response({"detail": contract_type_status[1]}, status=status.HTTP_400_BAD_REQUEST)

        contract_type_serializer_data = self.serializer_class(data=request.data)
        contract_type_serializer_data.is_valid(raise_exception=True)
        contract_type_serializer_data.save()
        return Response({'message': 'Contract type created successfully!', 'data': contract_type_serializer_data.data},
                        status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        contract_type_status = check_contract_type_valid(request.data, is_create=False)
        if not contract_type_status[0]:
            return Response({"detail": contract_type_status[1]}, status=status.HTTP_400_BAD_REQUEST)

        contract_object = models.ContractModel.objects.filter(contract_type=self.get_object().id)
        if contract_object.exists():
            return Response({"detail": "Contract Type Cannot Be Updated, As It Is Added To A Contract"},
                            status=status.HTTP_400_BAD_REQUEST)
            # ToDo : Need to allow contract type to be updated, if current flow for the request is completed.
        else:
            contract_type_serializer_data = self.serializer_class(data=request.data, partial=True)
            contract_type_object = self.get_object()
            contract_type_serializer_data.is_valid(raise_exception=True)
            if 'payment_terms' in request.data:
                payment_term_data = get_object_or_404(models.PaymentTermModel, id=request.data['payment_terms'],
                                                      is_delete=False)
                request.data['payment_terms'] = payment_term_data
            if 'fixed_fee_value' not in request.data:
                request.data['fixed_fee_value'] = None
            if 'fixed_fee_type' not in request.data:
                request.data['fixed_fee_type'] = None
            contract_type_serializer_data.update(contract_type_object, request.data)
            contract_data = self.serializer_class(contract_type_object).data
            contract_data['payment_terms'] = serializers.PaymentTermModelSerializer(
                contract_type_object.payment_terms).data
        return Response({'message': 'Contract type updated successfully!', 'data': contract_data},
                        status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        contract_type_object = self.get_object()
        contract_data = self.serializer_class(contract_type_object, context={
            "contract_id": self.request.query_params.get("contract_id")}).data
        contract_data['payment_terms'] = serializers.PaymentTermModelSerializer(contract_type_object.payment_terms).data

        return Response({'data': contract_data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        contract_object = get_object_or_404(models.ContractTypeModel, pk=kwargs['pk'], is_deleted=False)
        contract_object = self.get_object()
        if contract_object.contract_type.all().count() == 0:
            contract_object.is_deleted = True
            contract_object.save()
            return Response({"detail": "Contract Type Deleted Successfully."})
        else:
            return Response({"detail": "Contract Type Cannot Be Deleted, As It Is Added To A Contract"})

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset().filter(is_deleted=False))

        if page is not None:
            serializer = self.serializer_class(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)


class CalculateSalesAmount(APIView):
    """
    Class for calculating total sales amount
    """

    def post(self, request):
        if 'fund_invoice_id' not in request.data:
            return Response({
                "fund_invoice_id": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        if 'contract_id' not in request.data:
            return Response({
                "contract_id": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=request.data['fund_invoice_id'],
                                                is_deleted=False,
                                                fund_invoice_status__action_taken__contains=
                                                settings.CREDIT_REQUEST_CREATED)
        contract_object = get_object_or_404(models.ContractTypeModel, pk=request.data['contract_id'], is_deleted=False)
        total_sales_amount = calculate_total_sales_amount(fund_invoice_object, contract_object)
        output_dict = {'total_sales_amount': total_sales_amount[0],
                       'gross_margin': contract_object.gross_margin,
                       'markup': contract_object.markup,
                       'fixed_fee_type': contract_object.fixed_fee_type}
        if total_sales_amount[1]:
            output_dict['fixed_fee_value'] = total_sales_amount[1]
        else:
            output_dict['fixed_fee_value'] = 0
        return Response(output_dict, status=status.HTTP_200_OK)


class ContractModelViewSet(viewsets.ModelViewSet):
    """
    Class for CRUD operation for Contract data
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.ContractModelSerializer
    queryset = models.ContractModel.objects.all()
    http_method_names = ['get', 'post']

    def create(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            if 'contract_html_data' not in request.POST:
                return Response({"detail": "Contract file html template is needed for creating a contract"},
                                status=status.HTTP_400_BAD_REQUEST)
            # Checking if contract type selected is valid
            try:
                models.ContractTypeModel.objects.get(id=request.POST['contract_type'], is_deleted=False)
            except models.ContractTypeModel.DoesNotExist:
                return Response({'detail': 'Please check the contract type selected'},
                                status=status.HTTP_400_BAD_REQUEST)

            # # Validation needed till the generate signed contract is implemented, after that not needed
            # if 'supporting_docs' not in request.FILES:
            #     return Response({"detail": "Supporting docs is needed for creating a contract"},
            #                     status=status.HTTP_400_BAD_REQUEST)
            if 'fund_invoice' not in request.data:
                input_dict = request.POST.copy()
                try:
                    sme_user = User.objects.get(id=request.POST['sme'], user_role=settings.SME["number_value"],
                                                is_user_onboard=True, is_active=True)
                    if 'is_master_contract' not in request.POST:
                        return Response({"detail": "Type of contract is needed for creating a contract"},
                                        status=status.HTTP_400_BAD_REQUEST)
                except User.DoesNotExist:
                    return Response({'detail': 'Sorry you cannot add a master contract for this user'},
                                    status=status.HTTP_400_BAD_REQUEST)

                if sme_user.master_contract:
                    return Response({'detail': 'User cannot have more than one master contract'},
                                    status=status.HTTP_400_BAD_REQUEST)
                # Entering the data to ContractModel Table
                contract_serializer_data = self.serializer_class(data=input_dict, context={"request": request})
                contract_serializer_data.is_valid(raise_exception=True)
                contract_data = contract_serializer_data.save()
                # save master contract details to sme
                sme_user.master_contract = contract_data
                sme_user.save()

                # Saving additional cost details
                if 'additional_cost_data' in input_dict:
                    additional_cost_details = input_dict['additional_cost_data']
                    additional_cost_serializer = serializers.AdditionalContractCostSerializer(
                        data=eval(str(additional_cost_details)), many=True, context={"contract": contract_data})
                    additional_cost_serializer.is_valid(raise_exception=True)
                    additional_cost_serializer.save()

                # Replacing the html data from the FE for fixing the issue data shrinkage by replacing the font-size,
                # line-height and margin (in body tag)
                html_data = request.POST['contract_html_data'].replace('font-size:15px', 'font-size:18px').replace(
                    'line-height:2', 'line-height:1.6').replace('<body>', "<body style='margin:0'>")
                # Converting contract html template data to pdf and saving contract file data to DB
                pdf_path = f'{settings.USER_DATA}/{str(sme_user.id)}/' \
                           f'{settings.SIGNED_CONTRACT_FILES}/{settings.GENERATED_MASTER_CONTRACT_FILE_NAME}'
                # for creating a signed contract files folder
                if not os.path.exists(f'{settings.MEDIA_ROOT}/{settings.USER_DATA}/{str(sme_user.id)}/'
                                      f'{settings.SIGNED_CONTRACT_FILES}/'):
                    os.makedirs(f'{settings.MEDIA_ROOT}/{settings.USER_DATA}/{str(sme_user.id)}/'
                                f'{settings.SIGNED_CONTRACT_FILES}/')
                pdfkit.from_string(html_data, f'{settings.MEDIA_ROOT}/{pdf_path}', )
                contract_file_object = models.SignedContractFilesModel.objects.create(contract=contract_data,
                                                                                      contract_doc_type=
                                                                                      models.GENERATED_CONTRACT,
                                                                                      file_path=pdf_path,
                                                                                      action_by=request.user,
                                                                                      file_status=models.SIGNED_CONTRACT_ADDED)
                contract_file_object.save()
                status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_CREATED)
                master_contract_status_data = {"contract": contract_data.id, "action_taken": status_data[0],
                                               'action_by': request.user.id, 'assign_to': status_data[1]}

                notification_obj = models.NotificationModel.objects.filter(user_id=sme_user.id,
                                                                           type=settings.USER_ACTIVATED)
                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                status_serializer_data = serializers.MasterContractStatusSerializers(data=master_contract_status_data)

            else:
                try:
                    models.ContractModel.objects.get(fund_invoice=request.POST['fund_invoice'])
                    return Response({"detail": "Cannot add more than one contract against an fund invoice requested"},
                                    status=status.HTTP_400_BAD_REQUEST)
                except models.ContractModel.DoesNotExist:
                    pass

                if 'contract_html_data' not in request.POST:
                    return Response({"detail": "Contract file html template is needed for creating a contract"},
                                    status=status.HTTP_400_BAD_REQUEST)

                # Validation needed till the generate signed contract is implemented, after that not needed
                # if 'supporting_docs' not in request.FILES:
                #     return Response({"detail": "Supporting docs is needed for creating a contract"},
                #                     status=status.HTTP_400_BAD_REQUEST)

                # Checking if the factoring company added is valid
                input_dict = request.POST.copy()
                if 'factoring_company' in request.POST:
                    if input_dict['factoring_company'] == 'none':
                        input_dict['factoring_company'] = ''
                    else:
                        try:
                            User.objects.get(id=input_dict['factoring_company'], is_user_onboard=True,
                                             user_role=settings.FACTOR["number_value"], is_active=True)
                        except User.DoesNotExist:
                            return Response(
                                {'detail': 'Sorry you cannot add this factoring company for creating a contract'},
                                status=status.HTTP_400_BAD_REQUEST)

                queryset_filter = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_REQUEST_ADMIN_APPROVED,
                                                                         assign_to=settings.ADMIN[
                                                                             "name_value"]).exclude(
                    fund_invoice_status__action_taken__contains=
                    settings.CREDIT_CONTRACT_ADMIN_CREATED)
                fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=request.POST['fund_invoice'],
                                                        is_deleted=False)
                status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_CREATED)

                # Entering the data to ContractModel Table
                contract_serializer_data = self.serializer_class(data=input_dict, context={"request": request})
                contract_serializer_data.is_valid(raise_exception=True)
                contract_data = contract_serializer_data.save()

                # Saving additional cost details
                if 'additional_cost_data' in input_dict:
                    additional_cost_details = input_dict['additional_cost_data']
                    additional_cost_serializer = serializers.AdditionalContractCostSerializer(
                        data=eval(str(additional_cost_details)), many=True, context={"contract": contract_data})
                    additional_cost_serializer.is_valid(raise_exception=True)
                    additional_cost_serializer.save()

                # Replacing the html data from the FE for fixing the issue data shrinkage by replacing the font-size,
                # line-height and margin (in body tag)
                html_data = request.POST['contract_html_data'].replace('font-size:15px', 'font-size:18px').replace(
                    'line-height:2', 'line-height:1.6').replace('<body>', "<body style='margin:0'>")
                # Converting contract html template data to pdf and saving contract file data to DB
                pdf_path = f'{settings.FUND_INVOICE_DATA}/{str(fund_invoice_object.id)}/' \
                           f'{settings.SIGNED_CONTRACT_FILES}/{settings.GENERATED_CONTRACT_FILE_NAME}'
                # for creating a signed contract files folder
                if not os.path.exists(
                        f'{settings.MEDIA_ROOT}/{settings.FUND_INVOICE_DATA}/{str(fund_invoice_object.id)}/'
                        f'{settings.SIGNED_CONTRACT_FILES}/'):
                    os.makedirs(f'{settings.MEDIA_ROOT}/{settings.FUND_INVOICE_DATA}/{str(fund_invoice_object.id)}/'
                                f'{settings.SIGNED_CONTRACT_FILES}/')
                pdfkit.from_string(html_data, f'{settings.MEDIA_ROOT}/{pdf_path}', )
                contract_file_object = models.SignedContractFilesModel.objects.create(contract=contract_data,
                                                                                      contract_doc_type=models.
                                                                                      GENERATED_CONTRACT,
                                                                                      action_by=request.user,
                                                                                      file_path=pdf_path,
                                                                                      file_status=models.SIGNED_CONTRACT_ADDED)
                contract_file_object.save()

                # Entering the contract supporting docs to ContractSupportingDocsModel Table
                supporting_docs_list = list()
                for file_object in request.FILES.getlist('supporting_docs'):
                    supporting_docs_list.append(models.ContractSupportingDocsModel(contract=contract_data,
                                                                                   contract_file=file_object))
                models.ContractSupportingDocsModel.objects.bulk_create(supporting_docs_list)

                # Updating the FundInvoiceModel Table
                fund_invoice_object.assign_to = status_data[1]
                fund_invoice_object.save()

                # Entering the request data status to FundInvoiceStatusModel Table
                fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                            'action_by': request.user.id}
                status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
            status_serializer_data.is_valid(raise_exception=True)
            status_serializer_data.save()
            return Response({'message': 'Contract created successfully!', 'data': contract_serializer_data.data},
                            status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def retrieve(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = self.get_queryset().filter(Q(fund_invoice__is_deleted=False)
                                                         | Q(is_master_contract=True))
            contract_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_object, context={"request": request})
            output_data = serializer_data.data
            output_data['contract_type_data'] = serializers.ContractTypeModelSerializer(
                contract_object.contract_type, context={"contract_id": kwargs['pk']}).data
            output_data['contract_type_data']['payment_terms'] = serializers.PaymentTermModelSerializer(
                contract_object.contract_type.payment_terms,
                context={"contract_id": contract_object.id}).data
            output_data['contract_signed_file'] = serializers.SignedContractFilesSerializer(contract_object.
                                                                                            signed_contract_file.
                                                                                            filter(file_status=models.
                                                                                                   SIGNED_CONTRACT_ADDED),
                                                                                            many=True).data
            if contract_object.fund_invoice:
                output_data['invoice_grand_total'] = contract_object.fund_invoice.invoice_total_amount
                output_data["view_payment"] = contract_object.fund_invoice.fund_invoice_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
            return Response({'data': output_data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.SME["number_value"]:
            queryset_filter = self.get_queryset().filter(Q(fund_invoice__sme=request.user,
                                                           fund_invoice__is_deleted=False,
                                                           fund_invoice__fund_invoice_status__action_taken__contains=
                                                           settings.CREDIT_CONTRACT_ADMIN_SIGNED) |
                                                         Q(is_master_contract=True, sme_master_contract=request.user))
            # detail: "Not found" catch exception if query_set is None
            contract_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_data_object, context={"request": request})
            output_data = serializer_data.data
            output_data['contract_type_data'] = serializers.ContractTypeModelSerializer(
                contract_data_object.contract_type, context={"contract_id": kwargs['pk']}).data
            output_data['contract_type_data']['payment_terms'] = serializers.PaymentTermModelSerializer(
                contract_data_object.contract_type.payment_terms,
                context={"contract_id": contract_data_object.id}).data
            output_data['contract_signed_file'] = serializers.SignedContractFilesSerializer(contract_data_object.
                                                                                            signed_contract_file.
                                                                                            filter(file_status=models.
                                                                                                   SIGNED_CONTRACT_ADDED),
                                                                                            many=True).data
            if contract_data_object.fund_invoice:
                output_data['invoice_grand_total'] = contract_data_object.fund_invoice.invoice_total_amount
                output_data["view_payment"] = contract_data_object.fund_invoice.fund_invoice_status.all().filter(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()
            return Response({'data': output_data}, status=status.HTTP_200_OK)


        elif request.user.user_role == settings.FACTOR["number_value"]:
            queryset_filter = self.get_queryset().filter(factoring_company=request.user,
                                                         fund_invoice__is_deleted=False,
                                                         fund_invoice__fund_invoice_status__action_taken__contains=
                                                         settings.CREDIT_CONTRACT_ADMIN_SIGNED)
            contract_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_data_object, context={"request": request})
            output_data = serializer_data.data
            output_data['contract_type_data'] = serializers.ContractTypeModelSerializer(
                contract_data_object.contract_type).data
            output_data['contract_type_data']['payment_terms'] = serializers.PaymentTermModelSerializer(
                contract_data_object.contract_type.payment_terms,
                context={"contract_id": contract_data_object.id}).data

            output_data['invoice_grand_total'] = contract_data_object.fund_invoice.invoice_total_amount
            output_data['contract_signed_file'] = serializers.SignedContractFilesSerializer(contract_data_object.
                                                                                            signed_contract_file.
                                                                                            filter(file_status=models.
                                                                                                   SIGNED_CONTRACT_ADDED),
                                                                                            many=True).data
            output_data["view_payment"] = contract_data_object.fund_invoice.fund_invoice_status.all().filter(
                action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED).exists()

            return Response({'data': output_data}, status=status.HTTP_200_OK)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def list(self, request, *args, **kwargs):
        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")
        if request.user.user_role == settings.ADMIN["number_value"]:
            queryset_data = self.get_queryset().filter()
            if to_date and from_date:
                queryset_data = queryset_data.filter(date_created__lte=to_date, date_created__gte=from_date)
            if request.GET.get("next_action") == "pending_approval":
                queryset_data = queryset_data.filter(Q(fund_invoice__is_deleted=False,
                                                       fund_invoice__fund_invoice_status__action_taken__contains=
                                                       settings.CREDIT_CONTRACT_ADMIN_SIGNED) | Q(
                    is_master_contract=True,
                    master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)).exclude(Q(
                    fund_invoice__fund_invoice_status__action_taken__contains=
                    settings.CREDIT_CONTRACT_SME_APPROVED) | Q(
                    master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED))
            else:
                queryset_data = queryset_data.filter(Q(fund_invoice__is_deleted=False) | Q(is_master_contract=True))
            page = self.paginate_queryset(queryset_data)
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.SME["number_value"]:
            if to_date and from_date is not None:
                page = self.paginate_queryset(self.get_queryset().filter(Q(fund_invoice__sme=request.user,
                                                                           fund_invoice__is_deleted=False,
                                                                           fund_invoice__fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_ADMIN_SIGNED) |
                                                                         Q(is_master_contract=True,
                                                                           sme_master_contract=request.user),
                                                                         date_created__lte=to_date,
                                                                         date_created__gte=from_date))
            else:
                page = self.paginate_queryset(self.get_queryset().filter(Q(fund_invoice__sme=request.user,
                                                                           fund_invoice__is_deleted=False,
                                                                           fund_invoice__fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_ADMIN_SIGNED) |
                                                                         Q(is_master_contract=True,
                                                                           sme_master_contract=request.user)))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            if to_date and from_date is not None:
                page = self.paginate_queryset(self.get_queryset().filter(factoring_company=request.user,
                                                                         fund_invoice__is_deleted=False,
                                                                         fund_invoice__fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                         date_created__lte=to_date,
                                                                         date_created__gte=from_date))
            else:
                page = self.paginate_queryset(self.get_queryset().filter(factoring_company=request.user,
                                                                         fund_invoice__is_deleted=False,
                                                                         fund_invoice__fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_ADMIN_SIGNED))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


# class ContractSendToSme(APIView):
#     """
#     Class for sending(shown in contract listing) contract to SME
#     """
#     permission_classes = [IsCustomAdminUser]

#     def post(self, request):
#         contract_object = models.ContractModel.objects.get(id=request.data['contract_id'])
#         if contract_object.is_master_contract:
#             status_obj = models.MasterContractStatusModel.objects.filter(
#                 action_taken=settings.CREDIT_CONTRACT_ADMIN_SIGNED,
#                 assign_to=settings.ADMIN["name_value"],
#                 contract=contract_object).exclude(
#                 action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE)
#             if status_obj.exists():
#                 status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE)
#                 # Entering the request data status to MasterContractStatus Table
#                 master_contract_status_data = {"contract": contract_object.id, "action_taken": status_data[0],
#                                                'action_by': request.user.id, "assign_to": status_data[1]}
#                 status_serializer_data = serializers.MasterContractStatusSerializers(data=master_contract_status_data)
#             else:
#                 return Response({'message': 'Detail not found'}, status=status.HTTP_400_BAD_REQUEST)
#         else:
#             status_obj = models.FundInvoiceStatusModel.objects.filter(action_taken__contains=
#                                                                       settings.CREDIT_CONTRACT_ADMIN_SIGNED,
#                                                                       fund_invoice__is_deleted=False,
#                                                                       fund_invoice=contract_object.fund_invoice,
#                                                                       fund_invoice__assign_to=settings.ADMIN[
#                                                                           "name_value"]).exclude(
#                 action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE)

#             if status_obj.exists():
#                 status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_SEND_SME_DONE)

#                 # Updating the FundInvoiceModel Table
#                 fund_invoice_object = contract_object.fund_invoice
#                 fund_invoice_object.assign_to = status_data[1]
#                 fund_invoice_object.save()
#                 # Entering the request data status to FundInvoiceStatusModel Table
#                 fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
#                                             'action_by': request.user.id}
#                 status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
#             else:
#                 return Response({'message': 'Detail not found'}, status=status.HTTP_400_BAD_REQUEST)

#         status_serializer_data.is_valid(raise_exception=True)
#         status_serializer_data.save()
#         return Response({'message': 'Successfully sent the contract to SME'}, status=status.HTTP_200_OK)


class ContractSMEApproval(APIView):
    """
    Class for approving (signing) created contracts by SME
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_role == settings.SME["number_value"]:
            contract_object = models.ContractModel.objects.get(id=request.data['contract_id'])

            if contract_object.is_master_contract:
                if not request.user.master_contract == contract_object:
                    return Response({'message': 'Master contract doesnot belongs to this SME'},
                                    status=status.HTTP_200_OK)
                status_obj = models.MasterContractStatusModel.objects.filter(
                    action_taken=settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                    assign_to=settings.SME[
                        "name_value"],
                    contract=contract_object
                ).exclude(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)
                if status_obj.exists():
                    signed_contract_object = contract_object.signed_contract_file.all().filter(
                        contract_doc_type=models.SME_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_CREATED)
                    if not signed_contract_object.exists():
                        return Response({"detail": "Please finish the contract document signing"},
                                        status=status.HTTP_400_BAD_REQUEST)

                    status_data = generate_request_status(settings.CREDIT_CONTRACT_SME_APPROVED, True)
                    # Entering the request data status to MasterContractStatus Table
                    master_contract_status_data = {"contract": contract_object.id, "action_taken": status_data[0],
                                                   'action_by': request.user.id, "assign_to": status_data[1]}
                    status_serializer_data = serializers.MasterContractStatusSerializers(
                        data=master_contract_status_data)
                else:
                    return Response({'message': 'Detail not found'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                status_obj = models.FundInvoiceStatusModel.objects.filter(fund_invoice__sme=request.user,
                                                                          fund_invoice__is_deleted=False,
                                                                          action_taken__contains=
                                                                          settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                          fund_invoice=contract_object.fund_invoice,
                                                                          fund_invoice__assign_to=settings.SME[
                                                                              "name_value"]).exclude(
                    action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)

                fund_invoice_object = contract_object.fund_invoice
                signed_contract_object = contract_object.signed_contract_file.all().filter(
                    contract_doc_type=models.SME_SIGNED_CONTRACT,
                    file_status=models.SIGNED_CONTRACT_CREATED)
                if not signed_contract_object.exists():
                    return Response({"detail": "Please finish the contract document signing"},
                                    status=status.HTTP_400_BAD_REQUEST)

                status_data = generate_request_status(settings.CREDIT_CONTRACT_SME_APPROVED)

                # Updating the FundInvoiceModel Table
                fund_invoice_object.assign_to = status_data[1]
                fund_invoice_object.save()
                # Entering the request data status to FundInvoiceStatusModel Table
                fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                            'action_by': request.user.id}
                status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
            status_serializer_data.is_valid(raise_exception=True)
            status_serializer_data.save()

            # Updating signed contract file instance
            signed_contract_object.update(file_status=models.SIGNED_CONTRACT_ADDED)
            return Response({'message': 'Contract signed by SME'}, status=status.HTTP_200_OK)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class ContractAdminSign(APIView):
    """
    Class for signing the created contracts by Admin
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        contract_object = models.ContractModel.objects.get(id=request.data['contract_id'])
        signed_contract_object = None

        if contract_object.is_master_contract:
            status_obj = models.MasterContractStatusModel.objects.filter(
                action_taken=settings.CREDIT_CONTRACT_ADMIN_CREATED,
                assign_to=settings.ADMIN[
                    "name_value"], contract=contract_object).exclude(
                action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
            if status_obj.exists():
                signed_contract_object = contract_object.signed_contract_file.all().filter(
                    contract_doc_type=models.ADMIN_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_CREATED)
                if not signed_contract_object.exists():
                    return Response({"detail": "Please finish the contract document signing"},
                                    status=status.HTTP_400_BAD_REQUEST)

                status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_SIGNED)

                sme_reminder_mail(settings.SIGN_CONTRACT, contract_object.sme_master_contract.first_name,
                                  contract_object.sme_master_contract.email, contract_object.id)

                # Entering the request data status to MasterContractStatus Table
                master_contract_status_data = {"contract": contract_object.id, "action_taken": status_data[0],
                                               'action_by': request.user.id, "assign_to": status_data[1]}
                status_serializer_data = serializers.MasterContractStatusSerializers(data=master_contract_status_data)
            else:
                return Response({'message': 'Detail not found'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            status_obj = models.FundInvoiceStatusModel.objects.filter(action_taken__contains=
                                                                      settings.CREDIT_CONTRACT_ADMIN_CREATED,
                                                                      fund_invoice__is_deleted=False,
                                                                      fund_invoice=contract_object.fund_invoice,
                                                                      fund_invoice__assign_to=settings.ADMIN[
                                                                          "name_value"]).exclude(
                action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
            if status_obj.exists():
                fund_invoice_object = contract_object.fund_invoice
                signed_contract_object = contract_object.signed_contract_file.all().filter(contract_doc_type=
                                                                                           models.ADMIN_SIGNED_CONTRACT,
                                                                                           file_status=models.SIGNED_CONTRACT_CREATED)
                if not signed_contract_object.exists():
                    return Response({"detail": "Please finish the contract document signing"},
                                    status=status.HTTP_400_BAD_REQUEST)
                status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                sme_reminder_mail(settings.SIGN_CONTRACT, fund_invoice_object.sme.first_name,
                                  fund_invoice_object.sme.email, contract_object.id)

                # Updating the FundInvoiceModel Table
                fund_invoice_object.assign_to = status_data[1]
                fund_invoice_object.save()
                # Entering the request data status to FundInvoiceStatusModel Table
                fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                            'action_by': request.user.id}
                status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
            else:
                return Response({'message': 'Detail not found'}, status=status.HTTP_400_BAD_REQUEST)
        status_serializer_data.is_valid(raise_exception=True)
        status_serializer_data.save()

        # Updating signed contract file instance
        signed_contract_object.update(file_status=models.SIGNED_CONTRACT_ADDED, reminder_count=1)
        return Response({'message': 'Contract signed by Admin'}, status=status.HTTP_200_OK)


# class ContractSmeAcknowledgment(APIView):
#     """
#     Class for acknowledging contract by SME
#     """
#     permission_classes = [IsAuthenticated]
#
#     def post(self, request):
#         if request.user.user_role == settings.SME["number_value"]:
#             queryset_filter = models.ContractModel.objects.filter(
#                 fund_invoice__sme=request.user,
#                 fund_invoice__fund_invoice_status__action_taken__contains=
#                 settings.CREDIT_CONTRACT_ADMIN_APPROVED,
#                 fund_invoice__assign_to=settings.SME["name_value"]).exclude(
#                 fund_invoice__fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_ACKNOWLEDGED)
#             contract_object = get_object_or_404(queryset_filter, pk=request.data['contract_id'])
#             fund_invoice_object = contract_object.fund_invoice
#
#             status_data = generate_request_status(settings.CREDIT_CONTRACT_SME_ACKNOWLEDGED)
#
#             # Updating the FundInvoiceModel Table
#             # fund_invoice_object.assign_to = status_data[1]
#             # fund_invoice_object.save()
#
#             # Entering the request data status to FundInvoiceStatusModel Table
#             fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
#                                         'action_by': request.user.id}
#             if "remarks" in request.data:
#                 fund_invoice_status_data['remarks'] = request.data["remarks"]
#             status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
#             status_serializer_data.is_valid(raise_exception=True)
#             status_serializer_data.save()
#             return Response({'message': 'Successfully acknowledged the contract'}, status=status.HTTP_200_OK)
#         else:
#             return Response({"detail": "You do not have permission to perform this action."},
#                             status=status.HTTP_403_FORBIDDEN)


class ShipmentModelViewSet(viewsets.ModelViewSet):
    """
    Class for CRUD operation for Shipment data
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.ShipmentModelSerializer
    queryset = models.ShipmentModel.objects.all()
    http_method_names = ['get', 'post']

    def create(self, request, *args, **kwargs):
        if request.user.user_role == settings.SUPPLIER["number_value"] or \
                request.user.user_role == settings.SME["number_value"]:
            if int(request.data['number_of_shipments']) > 10:
                return Response({'Detail': 'Maximum 10 shipments are allowed. Please check that.'})
            if request.user.user_role == settings.SUPPLIER["number_value"]:
                queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                         Q(contract_category=
                                                                           settings.MASTER_CONTRACT['number_value']),
                                                                         supplier=request.user,
                                                                         is_deleted=False).exclude(
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_CREATED)
                    | Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_CREATED)).distinct()
                status_data = generate_request_status(settings.CREDIT_SHIPMENT_SUPPLIER_CREATED)
            else:
                queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                         Q(contract_category=
                                                                           settings.MASTER_CONTRACT['number_value']),
                                                                         sme=request.user, is_deleted=False).exclude(
                    Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_CREATED)
                    | Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_CREATED)).distinct()
                status_data = generate_request_status(settings.CREDIT_SHIPMENT_SME_CREATED)
            fund_invoice_object = get_object_or_404(queryset_filter, pk=request.POST['fund_invoice'])

            # Updating the FundInvoiceModel Table
            fund_invoice_object.assign_to = status_data[1]
            fund_invoice_object.save()

            notification_obj = models.NotificationModel.objects.filter(fund_invoice_id=request.POST['fund_invoice'],
                                                                       type=settings.FUND_REQUEST_APPROVED)

            if not notification_obj.exists():
                notification_obj = models.NotificationModel.objects.filter(contract_id=
                                                                           fund_invoice_object.contract_fund_invoice.first().id,
                                                                           type=settings.CREDIT_CONTRACT_SME_APPROVED)

            if notification_obj.exists():
                notification_obj.update(is_completed=True)

                # Entering the request data status to FundInvoiceStatusModel Table
            fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                        'action_by': request.user.id}
            status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
            status_serializer_data.is_valid(raise_exception=True)
            status_serializer_data.save()

            # Entering the data to ShipmentModel Table
            warning_messages = get_shipment_warning_message(fund_invoice_object,
                                                            fund_invoice_object.payment_fund_invoice.filter(
                                                                payment_made_by__user_role=settings.ADMIN_ROLE_VALUE,
                                                                payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN),
                                                            fund_invoice_object.supplier_term.supplier_terms.filter(
                                                                before_shipment=True))
            input_dict = request.POST.copy()
            input_dict["system_remarks"] = ', '.join(warning_messages)
            shipment_serializer_data = self.serializer_class(data=input_dict, context={"request": request})
            shipment_serializer_data.is_valid(raise_exception=True)
            shipment_data = shipment_serializer_data.save()
            if request.user.user_role == settings.SUPPLIER["number_value"]:

                notification_data = {"shipment": shipment_data.id, "notification": "Shipment was Added",
                                     "type": settings.SHIPMENT_ADDED_BY_SUPPLIER,
                                     "description": "Shipment Approval is Pending",
                                     "assignee": fund_invoice_object.sme.id}
            else:
                notification_data = {"shipment": shipment_data.id, "notification": "Shipment was Added",
                                     "type": settings.SHIPMENT_ADDED_BY_SME,
                                     "description": "Shipment Approval is Pending",
                                     "assignee": fund_invoice_object.supplier.id}

            notification_serializer = serializers.NotificationModelSerializer(data=notification_data)

            if notification_serializer.is_valid(raise_exception=True):
                notification_serializer.save()

            # Checking payment is pending or not
            payment_object = models.PaymentModel.objects.filter(fund_invoice=fund_invoice_object.id,
                                                                payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN)
            if not payment_object.exists():
                payment_notification = {
                    "shipment": shipment_data.id, "notification": "Shipment was Added, Payment pending",
                    "type": settings.SHIPMENT_ADDED_PAYMENT_PENDING,
                    "description": "Supplier payment is pending",
                    "assignee": None
                }
                payment_notification_serializer = serializers.NotificationModelSerializer(data=payment_notification)
                payment_notification_serializer.is_valid(raise_exception=True)
                payment_notification_serializer.save()

            # Entering the shipment files to ShipmentFilesModel Table
            country_model_ids = list()
            files_list = list()
            for ind, shipment_details in enumerate(eval(str(request.data.get('shipment_details')))):
                if shipment_details.get('id'):
                    country_obj = models.FundInvoiceCountryModel.objects.get(id=shipment_details['id'])
                    country_serializer = serializers.FundInvoiceCountryModelSerializer(country_obj, shipment_details)
                    country_serializer.is_valid(raise_exception=True)
                    country_serializer_data = country_serializer.save()
                else:
                    country_serializer = serializers.FundInvoiceCountryModelSerializer(data=shipment_details,
                                                                                       context={
                                                                                           'fund_invoice': fund_invoice_object})
                    country_serializer.is_valid(raise_exception=True)
                    country_serializer_data = country_serializer.save()
                country_model_ids.append(country_serializer_data.id)
                for doc_type in settings.SHIPMENT_DOC_KEY:
                    if doc_type != 'additional_doc' and request.FILES.get(doc_type + "_" + str(ind + 1)):
                        files_list.append(models.ShipmentFilesModel(country=country_serializer_data,
                                                                    shipment=shipment_data,
                                                                    shipment_number=ind + 1,
                                                                    document_type=doc_type,
                                                                    action_by=request.user,
                                                                    file_object=request.FILES[
                                                                        doc_type + "_" + str(ind + 1)]))
                if request.FILES.getlist('additional_doc_' + str(ind + 1)):
                    for additional_files in request.FILES.getlist('additional_doc_' + str(ind + 1)):
                        files_list.append(models.ShipmentFilesModel(country=country_serializer_data,
                                                                    shipment=shipment_data,
                                                                    shipment_number=ind + 1,
                                                                    document_type='additional_doc',
                                                                    action_by=request.user,
                                                                    file_object=additional_files))

            # files_list = list()
            # for shipment_number in range(int(request.data['number_of_shipments'])):
            #     for doc_type in settings.SHIPMENT_DOC_KEY:
            #         if doc_type + "_" + str(shipment_number + 1) in request.FILES:
            #             files_list.append(models.ShipmentFilesModel(shipment=shipment_data,
            #                                                         shipment_number=shipment_number + 1,
            #                                                         document_type=doc_type,
            #                                                         action_by=request.user,
            #                                                         file_object=request.FILES[
            #                                                             doc_type + "_" + str(shipment_number + 1)]))
            if 'file_label' in request.data:
                if request.data['file_label'] in request.data:
                    files_list.append(models.ShipmentFilesModel(
                        shipment=shipment_data,
                        shipment_number=0,
                        document_type=request.data['file_label'],
                        action_by=request.user,
                        file_object=request.FILES[request.data['file_label']]
                    ))
                else:
                    return Response({"Detail": f"Please add {request.data['file_label']} file."},
                                    status=status.HTTP_400_BAD_REQUEST)
            models.ShipmentFilesModel.objects.bulk_create(files_list)
            models.FundInvoiceCountryModel.objects.filter(fund_invoice_id=request.POST['fund_invoice']).exclude(
                id__in=country_model_ids).update(is_deleted=True)
            return Response({'message': 'Shipment added successfully!', 'data': shipment_serializer_data.data},
                            status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def retrieve(self, request, *args, **kwargs):
        if request.user.user_role == settings.SUPPLIER["number_value"]:
            queryset_filter = self.get_queryset().filter(fund_invoice__supplier=request.user,
                                                         fund_invoice__is_deleted=False)
            shipment_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(shipment_data_object, context={"request": request})
            output_data = serializer_data.data
            return Response({'data': output_data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.SME["number_value"]:
            queryset_filter = self.get_queryset().filter(fund_invoice__sme=request.user,
                                                         fund_invoice__is_deleted=False)
            shipment_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(shipment_data_object, context={"request": request})
            output_data = serializer_data.data
            if shipment_data_object.fund_invoice.contract_category == \
                    settings.MASTER_CONTRACT['number_value']:
                output_data['contract_number'] = shipment_data_object.fund_invoice.sme.master_contract.contract_number
            else:
                output_data['contract_number'] = shipment_data_object.fund_invoice.contract_fund_invoice.all()[
                    0].contract_number
            return Response({'data': output_data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = self.get_queryset().filter(fund_invoice__is_deleted=False)
            shipment_obj = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(shipment_obj, context={"request": request})
            output_data = serializer_data.data
            if shipment_obj.fund_invoice.contract_category == \
                    settings.MASTER_CONTRACT['number_value']:
                output_data['contract_number'] = shipment_obj.fund_invoice.sme.master_contract.contract_number
            else:
                output_data['contract_number'] = shipment_obj.fund_invoice.contract_fund_invoice.all()[
                    0].contract_number
            return Response({'data': output_data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            queryset_filter = self.get_queryset().filter(fund_invoice__contract_fund_invoice__factoring_company=
                                                         request.user, fund_invoice__is_deleted=False)
            shipment_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(shipment_data_object, context={"request": request})
            output_data = serializer_data.data
            output_data['contract_number'] = shipment_data_object.fund_invoice.contract_fund_invoice.all()[
                0].contract_number
            return Response({'data': output_data}, status=status.HTTP_200_OK)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def list(self, request, *args, **kwargs):
        return Response({"detail": "You do not have permission to perform this action."},
                        status=status.HTTP_403_FORBIDDEN)


class ShipmentAcknowledgment(APIView):
    """
    Class for acknowledging shipment by SME/Supplier
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, **kwargs):
        if request.user.user_role == settings.SME["number_value"]:
            if 'remarks' not in request.data:
                return Response({'message': "Please add a SME remarks"}, status=status.HTTP_400_BAD_REQUEST)

            shipment_object = get_object_or_404(models.ShipmentModel, id=request.data['shipment_id'],
                                                fund_invoice__sme=request.user, fund_invoice__assign_to=
                                                settings.SME["name_value"],
                                                fund_invoice__is_deleted=False)

            if shipment_object.fund_invoice.fund_invoice_status.first().action_taken == \
                    settings.CREDIT_SHIPMENT_SUPPLIER_CREATED or \
                    settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SUPPLIER_UPLOADED:
                if kwargs['user_action'] == settings.SHIPMENT_ACKNOWLEDGED:
                    status_data = generate_request_status(settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED)
                    response_message = {'message': 'Shipment acknowledged by SME'}
                elif kwargs['user_action'] == settings.SHIPMENT_SEND_BACK:
                    status_data = generate_request_status(settings.CREDIT_SHIPMENT_SME_SEND_BACK)
                    shipment_send_back_email(subject=settings.EMAIL_SHIPMENT_SEND_BACK,
                                             id=shipment_object.fund_invoice.id,
                                             recipient_email=shipment_object.fund_invoice.supplier.email,
                                             remarks=request.data["remarks"],
                                             recipient_name=shipment_object.fund_invoice.supplier.first_name,
                                             sender_name=request.user.first_name)
                    notification_data = {"shipment": shipment_object.id, "notification": "Shipment Send back by SME",
                                         "type": settings.SHIPMENT_SEND_BACK_BY_SME,
                                         "description": "Additional File Upload is Pending",
                                         "assignee": shipment_object.fund_invoice.supplier.id}

                    response_message = {'message': 'Shipment send back to the supplier'}
                    notification_serializer = serializers.NotificationModelSerializer(data=notification_data)
                    if notification_serializer.is_valid(raise_exception=True):
                        notification_serializer.save()
                        # Updating the FundInvoiceModel Table
                shipment_object.fund_invoice.assign_to = status_data[1]
                shipment_object.fund_invoice.save()

                # # Entering the request data status to FundInvoiceStatusModel Table
                fund_invoice_status_data = {"fund_invoice": shipment_object.fund_invoice.id,
                                            "action_taken": status_data[0],
                                            'action_by': request.user.id, 'remarks': request.data["remarks"]}
                status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()
                notification_obj = models.NotificationModel.objects.filter(Q(type=settings.SHIPMENT_ADDED_BY_SUPPLIER) |
                                                                           Q(type=settings.SHIPMENT_ADDITIONAL_FILE_ADDED_BY_SUPPLIER),
                                                                           shipment_id=shipment_object.id,
                                                                           is_completed=False)

                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                return Response({'message': response_message}, status=status.HTTP_200_OK)
            else:
                return Response({'message': "please check the selected action"}, status=status.HTTP_400_BAD_REQUEST)

        elif request.user.user_role == settings.SUPPLIER["number_value"]:
            if 'remarks' not in request.data:
                return Response({'message': "Please add a Suppler remarks"}, status=status.HTTP_400_BAD_REQUEST)
            shipment_object = get_object_or_404(models.ShipmentModel, id=request.data['shipment_id'],
                                                fund_invoice__supplier=request.user,
                                                fund_invoice__assign_to=settings.SUPPLIER["name_value"],
                                                fund_invoice__is_deleted=False)
            if shipment_object.fund_invoice.fund_invoice_status.first().action_taken == \
                    settings.CREDIT_SHIPMENT_SME_CREATED or settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SME_UPLOADED:
                if kwargs['user_action'] == settings.SHIPMENT_ACKNOWLEDGED:
                    status_data = generate_request_status(settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED)
                    response_message = {'message': 'Shipment acknowledged by Supplier'}
                elif kwargs['user_action'] == settings.SHIPMENT_SEND_BACK:
                    status_data = generate_request_status(settings.CREDIT_SHIPMENT_SUPPLIER_SEND_BACK)
                    response_message = {'message': 'Shipment send back to the sme'}
                    shipment_send_back_email(subject=settings.EMAIL_SHIPMENT_SEND_BACK,
                                             id=shipment_object.fund_invoice.id,
                                             recipient_email=shipment_object.fund_invoice.sme.email,
                                             remarks=request.data["remarks"],
                                             recipient_name=shipment_object.fund_invoice.sme.first_name,
                                             sender_name=request.user.first_name)
                    notification_data = {"shipment": shipment_object.id,
                                         "notification": "Shipment Send back by Supplier",
                                         "type": settings.SHIPMENT_SEND_BACK_BY_SUPPLIER,
                                         "description": "Additional File Upload is Pending",
                                         "assignee": shipment_object.fund_invoice.sme.id}

                    notification_serializer = serializers.NotificationModelSerializer(data=notification_data)
                    if notification_serializer.is_valid(raise_exception=True):
                        notification_serializer.save()
                        # Updating the FundInvoiceModel Table
                shipment_object.fund_invoice.assign_to = status_data[1]
                shipment_object.fund_invoice.save()
                # Entering the request data status to FundInvoiceStatusModel Table

                notification_obj = models.NotificationModel.objects.filter(Q(type=settings.SHIPMENT_ADDED_BY_SME) |
                                                                           Q(type=settings.SHIPMENT_ADDITIONAL_FILE_ADDED_BY_SME),
                                                                           shipment_id=shipment_object.id,
                                                                           is_completed=False)

                if notification_obj.exists():
                    notification_obj.update(is_completed=True)

                fund_invoice_status_data = {"fund_invoice": shipment_object.fund_invoice.id,
                                            "action_taken": status_data[0],
                                            'action_by': request.user.id, "remarks": request.data["remarks"]}
                status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()
                return Response({'message': response_message}, status=status.HTTP_200_OK)
            else:
                return Response({'message': "please check the selected action"}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


# class ShipmentAdminApproval(APIView):
#     """
#     Class for approving the SME acknowledged shipments by Admin
#     """
#     permission_classes = [IsCustomAdminUser]

#     def post(self, request, **kwargs):
#         shipment_object = get_object_or_404(models.ShipmentModel, id=request.data['shipment_id'])
#         if kwargs['admin_action'] == settings.SHIPMENT_APPROVED:
#             status_data = generate_request_status(settings.CREDIT_SHIPMENT_ADMIN_APPROVED)
#             response_message = {'message': 'Shipment approved by admin'}
#         elif kwargs['admin_action'] == settings.SHIPMENT_REJECTED:
#             status_data = generate_request_status(settings.CREDIT_SHIPMENT_ADMIN_REJECTED)
#             response_message = {'message': 'Shipment rejected by admin'}
#         else:
#             return Response(status=status.HTTP_404_NOT_FOUND)

#         queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
#                                                                    settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED) |
#                                                                  Q(fund_invoice_status__action_taken__contains=
#                                                                    settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED),
#                                                                  assign_to=settings.ADMIN["name_value"])

#         fund_invoice_object = get_object_or_404(queryset_filter, pk=shipment_object.fund_invoice.id)

#         # Updating the FundInvoiceModel Table
#         fund_invoice_object.assign_to = status_data[1]
#         fund_invoice_object.save()

#         # Entering the request data status to FundInvoiceStatusModel Table
#         fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
#                                     'action_by': request.user.id}
#         if "remarks" in request.data:
#             fund_invoice_status_data['remarks'] = request.data["remarks"]
#         status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
#         status_serializer_data.is_valid(raise_exception=True)
#         status_serializer_data.save()
#         return Response(response_message, status=status.HTTP_200_OK)


class ReadContractFile(APIView):
    """
    Class for reading contract file and sending the data
    """

    def post(self, request):
        if 'fund_invoice' in request.data:
            fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=request.data['fund_invoice'],
                                                    is_deleted=False)
            output_data = {'sme_company_no': fund_invoice_object.sme.on_boarding_details.company_registration_id}
            sme_leads_object = contact_app_models.LeadsModel.objects.filter(
                sign_up_email=fund_invoice_object.sme.email)
            if sme_leads_object.exists():
                output_data['sme_country'] = sme_leads_object[0].company_registered_in.name
            contract_file_path = f"{settings.DJANGO_ROOT_DIR}/{settings.CONTRACT_TEMPLATE_FILE_PATH}"
            with open(contract_file_path, 'r') as f:
                file_data = f.read()

        elif "sme" in request.data:

            sme_user_object = get_object_or_404(User, pk=request.data['sme'],
                                                is_deleted=False)
            output_data = {'sme_company_no': sme_user_object.on_boarding_details.company_registration_id}
            sme_leads_object = contact_app_models.LeadsModel.objects.filter(
                sign_up_email=sme_user_object.email)
            if sme_leads_object.exists():
                output_data['sme_country'] = sme_leads_object.first().company_registered_in.name
            try:
                account_details = models.AccountDetailsModel.objects.filter().first()
            except:
                return Response({"message": "Account details not added"}, status=status.HTTP_400_BAD_REQUEST)

            output_data['account_no'] = account_details.account_no
            output_data['sort_code'] = account_details.sort_code
            output_data['sterling'] = account_details.sterling
            output_data['euros'] = account_details.euros
            output_data['us_dollar'] = account_details.us_dollar
            contract_file_path = f"{settings.DJANGO_ROOT_DIR}/{settings.MASTER_CONTRACT_TEMPLATE_FILE_PATH}"
            with open(contract_file_path, 'r') as f:
                file_data = f.read()
        else:
            return Response({"message": "please check the input"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"meta_data": output_data, "data": file_data}, status=status.HTTP_200_OK)


class GetInvoiceDetails(APIView):
    """
    Class for getting the invoice details for payment view
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, **kwargs):
        if request.user.user_role == settings.SUPPLIER["number_value"]:
            queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                       settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                     Q(contract_category=
                                                                       settings.MASTER_CONTRACT['number_value']),
                                                                     supplier=request.user,
                                                                     is_deleted=False).distinct()

        elif request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                       settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                     Q(contract_category=
                                                                       settings.MASTER_CONTRACT['number_value']),
                                                                     is_deleted=False).distinct()
        elif request.user.user_role == settings.SME["number_value"]:
            queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                       settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                     Q(contract_category=
                                                                       settings.MASTER_CONTRACT['number_value']),
                                                                     sme=request.user,
                                                                     is_deleted=False).distinct()
        elif request.user.user_role == settings.FACTOR["number_value"]:
            queryset_filter = models.FundInvoiceModel. \
                objects.filter(fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED,
                               contract_fund_invoice__factoring_company=request.user, is_deleted=False)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

        fund_invoice_object = get_object_or_404(queryset_filter, pk=kwargs['fund_invoice_id'])
        output_dict = {"sme": fund_invoice_object.sme.on_boarding_details.company_name,
                       "supplier": fund_invoice_object.supplier.on_boarding_details.company_name,
                       "invoice_amount": fund_invoice_object.invoice_total_amount,
                       "invoice_date": fund_invoice_object.invoice_date,
                       "invoice_number": fund_invoice_object.invoice_number}
        if request.user.user_role in [settings.ADMIN["number_value"], settings.SME["number_value"],
                                      settings.FACTOR["number_value"]]:
            if fund_invoice_object.total_sales_amount is not None:
                output_dict["total_sales_amount"] = fund_invoice_object.total_sales_amount
            else:
                output_dict["total_sales_amount"] = fund_invoice_object.contract_fund_invoice.first().total_sales_amount
        return Response({'result': output_dict}, status=status.HTTP_200_OK)


class PaymentActionDetails(APIView):
    """
    Class for checking user actions and balance amount for a given payment type
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payment_type = self.request.query_params.get('payment_type')
        fund_invoice = self.request.query_params.get('fund_invoice')
        if not fund_invoice or not payment_type:
            return Response({"detail": "Please add the needed parameters (payment_type and fund_invoice)"},
                            status=status.HTTP_400_BAD_REQUEST)

        output_dict = dict()
        if request.user.user_role == settings.SUPPLIER["number_value"]:
            # Check for the payment type
            if int(payment_type) != models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
                return Response({
                    "detail": "Please check the payment type entered"}, status=status.HTTP_400_BAD_REQUEST)
            fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=int(fund_invoice),
                                                    supplier=request.user, is_deleted=False)
            payment_object = fund_invoice_object.payment_fund_invoice.filter(payment_type=int(payment_type))
            output_dict["can_create_payment"] = False
            if payment_object.exists():
                serializer_data = serializers.PaymentModelSerializer(payment_object[0],
                                                                     context={'request': request}).data
                output_dict["next_step"] = serializer_data["next_step"]
            else:
                output_dict["next_step"] = settings.REQUEST_NO_ACTION_NEEDED
            balance_amount = get_payment_balance_amount(fund_invoice_object, int(payment_type))
            output_dict["balance_amount"] = balance_amount[2]

        elif request.user.user_role == settings.SME["number_value"]:
            # Check for the payment type
            if int(payment_type) not in [models.PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                         models.PAYMENT_TO_SUPPLIER_BY_ADMIN]:
                return Response({"detail": "Please enter the correct payment type parameter"},
                                status=status.HTTP_400_BAD_REQUEST)
            fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=int(fund_invoice),
                                                    sme=request.user, is_deleted=False)
            if int(payment_type) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
                output_dict = payment_to_factor_details(fund_invoice_object, request)
            else:
                balance_amount = get_payment_balance_amount(fund_invoice_object, int(payment_type))
                output_dict["balance_amount"] = balance_amount[2]
                payment_object = fund_invoice_object.payment_fund_invoice.filter(payment_made_by__user_role=settings.
                                                                                 SME_ROLE_VALUE,
                                                                                 payment_type=int(payment_type))
                output_dict["can_create_payment"] = False
                if payment_object.exists():
                    serializer_data = serializers.PaymentModelSerializer(payment_object[0],
                                                                         context={'request': request}).data
                    output_dict["next_step"] = serializer_data["next_step"]
                else:
                    output_dict["next_step"] = settings.REQUEST_NO_ACTION_NEEDED

        elif request.user.user_role == settings.ADMIN["number_value"]:
            fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=int(fund_invoice),
                                                    is_deleted=False)
            if int(payment_type) == models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
                output_dict = payment_to_supplier_details(fund_invoice_object, request)
            elif int(payment_type) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
                balance_amount = get_payment_balance_amount(fund_invoice_object, int(payment_type))
                output_dict["balance_amount"] = balance_amount[2]
                output_dict["can_create_payment"] = False
                payment_object = fund_invoice_object.payment_fund_invoice.filter(payment_type=int(payment_type))
                if payment_object.exists():
                    serializer_data = serializers.PaymentModelSerializer(payment_object[0],
                                                                         context={'request': request}).data
                    output_dict["next_step"] = serializer_data["next_step"]
                else:
                    output_dict["next_step"] = settings.REQUEST_NO_ACTION_NEEDED
            elif int(payment_type) == models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY:
                output_dict = payment_to_admin_details(fund_invoice_object, request)
            else:
                return Response({"detail": "Please enter the correct payment type parameter"},
                                status=status.HTTP_400_BAD_REQUEST)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=int(fund_invoice),
                                                    contract_fund_invoice__factoring_company=request.user,
                                                    is_deleted=False)
            balance_amount = get_payment_balance_amount(fund_invoice_object, int(payment_type))
            output_dict["balance_amount"] = balance_amount[2]
            if int(payment_type) == models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
                output_dict["can_create_payment"] = False
                payment_object = fund_invoice_object.payment_fund_invoice.filter(payment_type=int(payment_type))
                if payment_object.exists():
                    serializer_data = serializers.PaymentModelSerializer(payment_object[0],
                                                                         context={'request': request}).data
                    output_dict["next_step"] = serializer_data["next_step"]
                else:
                    output_dict["next_step"] = settings.REQUEST_NO_ACTION_NEEDED
            elif int(payment_type) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
                output_dict["can_create_payment"] = False
                payment_object = fund_invoice_object.payment_fund_invoice.filter(payment_type=int(payment_type))
                if payment_object.exists():
                    serializer_data = serializers.PaymentModelSerializer(payment_object[0],
                                                                         context={'request': request}).data
                    output_dict["next_step"] = serializer_data["next_step"]
                else:
                    output_dict["next_step"] = settings.REQUEST_NO_ACTION_NEEDED
            elif int(payment_type) == models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY:
                del output_dict["balance_amount"]
                output_dict = payment_to_admin_details(fund_invoice_object, request)
            else:
                return Response({"detail": "Please enter the correct payment type parameter"},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

        return Response({'data': output_dict}, status=status.HTTP_200_OK)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Class for create, list and retrieve PaymentModel
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.PaymentModelSerializer
    queryset = models.PaymentModel.objects.all()
    http_method_names = ['get', 'post']

    def create(self, request, *args, **kwargs):
        if float(request.POST['paying_amount']) <= 0:
            return Response({"detail": "Please enter amount higher than 0"},
                            status=status.HTTP_400_BAD_REQUEST)
        if float(request.POST['tax_amount']) < 0:
            return Response({"detail": "Please enter amount higher than 0"},
                            status=status.HTTP_400_BAD_REQUEST)

        if request.user.user_role == settings.ADMIN["number_value"]:
            # Check for permission for the given payment type
            if int(request.POST['payment_type']) not in [models.PAYMENT_TO_SUPPLIER_BY_ADMIN,
                                                         models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY]:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
            queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                       settings.CREDIT_CONTRACT_SME_APPROVED) | Q
                                                                     (contract_category=settings.MASTER_CONTRACT[
                                                                         "number_value"])) \
                .distinct()
            fund_invoice_object = get_object_or_404(queryset_filter, pk=request.POST['fund_invoice'], is_deleted=False)
            if int(request.POST['payment_type']) == models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
                warning_details = payment_to_supplier_details(fund_invoice_object, request)
                term_order = warning_details['term_order']
                warning_messages = warning_details['warning_message']
                is_adhoc = warning_details['is_adhoc']
                warning_issues = list()
                # Check for the balance amount with new payment added
                if round(float(request.POST['paying_amount']), 3) > round(warning_details['balance_amount'], 3):
                    warning_issues.append("payment_balance_issue")
                # Check for the term amount with new payment added
                if "terms" in warning_details:
                    if round(float(request.POST['paying_amount']), 3) != round(warning_details['terms']['term_amount'],
                                                                               3):
                        warning_issues.append("term_payment_issue")
                warning_adhoc = get_payment_warning_message(warning_issues)
                warning_messages.extend(warning_adhoc[0])
            else:
                warning_details = payment_to_admin_details(fund_invoice_object, request)
                term_order = warning_details['term_order']
                warning_messages = warning_details['warning_message']
                is_adhoc = warning_details['is_adhoc']
        else:
            if request.user.user_role == settings.SME["number_value"]:
                # Check for permission for the given payment type
                if int(request.POST['payment_type']) != models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
                    return Response({"detail": "You do not have permission to perform this action."},
                                    status=status.HTTP_403_FORBIDDEN)
                queryset_filter = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                         Q(contract_category=settings.MASTER_CONTRACT[
                                                                             "number_value"]),
                                                                         sme=request.user).distinct()
                fund_invoice_object = get_object_or_404(queryset_filter, pk=request.POST['fund_invoice'],
                                                        is_deleted=False)
                warning_details = payment_to_factor_details(fund_invoice_object, request)
                warning_messages = warning_details['warning_message']
                is_adhoc = warning_details['is_adhoc']
                term_order = warning_details['term_order']
                warning_issues = list()
                # Check for the balance amount with new payment added
                if round(float(request.POST['paying_amount']), 3) > round(warning_details['balance_amount'], 3):
                    warning_issues.append("payment_balance_issue")
                # Check for the term amount with new payment added
                if "terms" in warning_details:
                    if round(float(request.POST['paying_amount']), 3) != round(warning_details['terms']['term_amount'],
                                                                               3):
                        warning_issues.append("term_payment_issue")
                warning_adhoc = get_payment_warning_message(warning_issues)
                warning_messages.extend(warning_adhoc[0])
            elif request.user.user_role == settings.FACTOR["number_value"]:
                if int(request.POST['payment_type']) != models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY:
                    return Response({"detail": "You do not have permission to perform this action."},
                                    status=status.HTTP_403_FORBIDDEN)
                queryset_filter = models.FundInvoiceModel.objects.filter(
                    fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED,
                    contract_fund_invoice__factoring_company=request.user)
                fund_invoice_object = get_object_or_404(queryset_filter, pk=request.POST['fund_invoice'],
                                                        is_deleted=False)
                warning_details = payment_to_admin_details(fund_invoice_object, request)
                term_order = warning_details['term_order']
                warning_messages = warning_details['warning_message']
                is_adhoc = warning_details['is_adhoc']
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
        if 'payment_files' not in request.FILES:
            return Response({"detail": "Please add a file showing the payment details"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Entering the data to PaymentModel Table
        input_dict = request.POST.copy()
        input_dict["system_remarks"] = ', '.join(warning_messages)
        input_dict["is_adhoc"] = is_adhoc
        input_dict["term_order"] = term_order
        input_dict["payment_made_by"] = request.user.id
        if int(input_dict['payment_type']) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
            input_dict["acknowledgement_status"] = models.CREDIT_PAYMENT_PAID
            input_dict["acknowledgement_completed"] = True
        else:
            input_dict["acknowledgement_status"] = models.CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING
        payment_serializer_data = self.serializer_class(data=input_dict, context={"request": request})
        payment_serializer_data.is_valid(raise_exception=True)
        payment_data = payment_serializer_data.save()

        # Entering the payment files to PaymentFilesModel Table
        payment_files_list = list()
        for file_object in request.FILES.getlist('payment_files'):
            payment_files_list.append(models.PaymentFilesModel(payment=payment_data, payment_file=file_object))
        models.PaymentFilesModel.objects.bulk_create(payment_files_list)

        # Entering the request data status to PaymentStatusModel Table
        payment_status_data = {"action_taken": models.CREDIT_PAYMENT_ADDED,
                               'action_by': request.user.id,
                               "payment": payment_data.id}
        status_serializer_data = serializers.PaymentStatusModelSerializer(data=payment_status_data)
        status_serializer_data.is_valid(raise_exception=True)
        status_serializer_data.save()
        if int(request.POST['payment_type']) == models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
            payment_acknowledgment_mail(settings.PAYMENT_ACKNOWLEDGE_SUPPLIER, fund_invoice_object.supplier.first_name,
                                        settings.SENDER_NAME, fund_invoice_object.supplier.email,
                                        request.POST['paying_amount'], request.POST['payment_ref_number'])
            payment_acknowledgment_mail_sme(settings.PAYMENT_ACKNOWLEDGE_SUPPLIER, fund_invoice_object.sme.first_name,
                                            settings.SENDER_NAME, fund_invoice_object.supplier.first_name,
                                            fund_invoice_object.sme.email)
        return Response({'message': 'Payment added successfully!', 'data': payment_serializer_data.data},
                        status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = self.get_queryset().filter(fund_invoice__is_deleted=False)
            contract_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_object, context={"request": request})
            return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.SME["number_value"]:

            queryset_filter = self.get_queryset().filter(fund_invoice__sme=request.user,
                                                         fund_invoice__is_deleted=False).filter(
                Q(payment_type=models.PAYMENT_TO_FACTORING_COMPANY_BY_SME) |
                Q(payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN))
            contract_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_data_object, context={"request": request})
            return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.SUPPLIER["number_value"]:
            queryset_filter = self.get_queryset().filter(payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN,
                                                         fund_invoice__supplier=request.user,
                                                         fund_invoice__is_deleted=False)
            contract_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_data_object, context={"request": request})
            return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            queryset_filter = self.get_queryset().filter(fund_invoice__contract_fund_invoice__factoring_company=
                                                         request.user,
                                                         fund_invoice__is_deleted=False)
            contract_data_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(contract_data_object, context={"request": request})
            return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def list(self, request, *args, **kwargs):
        payment_type = self.request.query_params.get('payment_type')
        fund_invoice = self.request.query_params.get('fund_invoice')
        if not fund_invoice or not payment_type:
            return Response({"detail": "Please add the needed parameters (payment_type and fund_invoice)"},
                            status=status.HTTP_400_BAD_REQUEST)
        if request.user.user_role == settings.ADMIN["number_value"]:
            page = self.paginate_queryset(self.get_queryset().filter(payment_type=payment_type,
                                                                     fund_invoice=fund_invoice,
                                                                     fund_invoice__is_deleted=False))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.SME["number_value"]:
            if int(payment_type) not in [models.PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                         models.PAYMENT_TO_SUPPLIER_BY_ADMIN]:
                return Response({"detail": "Please enter the correct payment type parameter"},
                                status=status.HTTP_400_BAD_REQUEST)
            page = self.paginate_queryset(self.get_queryset().filter(payment_type=payment_type,
                                                                     fund_invoice=fund_invoice,
                                                                     fund_invoice__sme=request.user,
                                                                     fund_invoice__is_deleted=False))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.SUPPLIER["number_value"]:
            if int(payment_type) != models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
                return Response({"detail": "Please enter the correct payment type parameter"},
                                status=status.HTTP_400_BAD_REQUEST)
            page = self.paginate_queryset(self.get_queryset().filter(payment_type=payment_type,
                                                                     fund_invoice=fund_invoice,
                                                                     fund_invoice__supplier=request.user,
                                                                     fund_invoice__is_deleted=False))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            page = self.paginate_queryset(self.get_queryset().
                                          filter(payment_type=payment_type,
                                                 fund_invoice=fund_invoice,
                                                 fund_invoice__contract_fund_invoice__factoring_company=request.user,
                                                 fund_invoice__is_deleted=False))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


#
# class PaymentStatusUpdate(APIView):
#     """
#     Class for updating the status of the payment by the payment creator
#     """
#     permission_classes = [IsAuthenticated]
#
#     def post(self, request):
#         if request.user.user_role == settings.ADMIN["number_value"]:
#             queryset_filter = models.PaymentModel.objects.filter(payment_made_by__user_role=request.user.user_role). \
#                 exclude(Q(payment_status=int(request.data['payment_status'])) |
#                         Q(payment_status=models.PAYMENT_STATUS_COMPLETED))
#         else:
#             queryset_filter = models.PaymentModel.objects.filter(Q(payment_made_by=request.user) |
#                                                                  Q(payment_made_by__user_role=request.user.user_role)). \
#                 exclude(Q(payment_status=int(request.data['payment_status'])) |
#                         Q(payment_status=models.PAYMENT_STATUS_COMPLETED))
#         payment_object = get_object_or_404(queryset_filter, pk=request.data['payment_id'])
#         payment_object.payment_status = int(request.data['payment_status'])
#         payment_object.save()
#         return Response({'message': 'Payment status updated successfully!'}, status=status.HTTP_200_OK)


class PaymentAcknowledge(APIView):
    """
    Class for acknowledging the payment status by the user
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_role == settings.ADMIN["number_value"]:
            if int(request.data["payment_type"]) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
                queryset_filter = models.PaymentModel.objects.filter(
                    payment_made_by__user_role=settings.SME["number_value"],
                    payment_type=int(request.data["payment_type"]),
                    fund_invoice__is_deleted=False,
                    acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGED_BY_FACTOR). \
                    exclude(acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGED_BY_ADMIN)
                acknowledgement_status = models.CREDIT_PAYMENT_ACKNOWLEDGED_BY_ADMIN
                acknowledgement_completed = True
            elif int(request.data["payment_type"]) == models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY:
                queryset_filter = models.PaymentModel.objects.filter(
                    payment_made_by__user_role=settings.FACTOR["number_value"],
                    payment_type=int(request.data["payment_type"]),
                    fund_invoice__is_deleted=False,
                    acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING)
                acknowledgement_status = models.CREDIT_PAYMENT_ACKNOWLEDGED
                acknowledgement_completed = True
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
        elif request.user.user_role == settings.FACTOR["number_value"]:
            if int(request.data["payment_type"]) == models.PAYMENT_TO_FACTORING_COMPANY_BY_SME:
                queryset_filter = models.PaymentModel.objects.filter(
                    payment_made_by__user_role=settings.SME["number_value"],
                    payment_type=int(request.data["payment_type"]),
                    fund_invoice__is_deleted=False,
                    acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING)
                acknowledgement_status = models.CREDIT_PAYMENT_ACKNOWLEDGED_BY_FACTOR
                acknowledgement_completed = False
            elif int(request.data["payment_type"]) == models.PAYMENT_TO_ADMIN_BY_FACTORING_COMPANY:
                queryset_filter = models.PaymentModel.objects.filter(
                    payment_made_by__user_role=settings.ADMIN["number_value"],
                    payment_type=int(request.data["payment_type"]),
                    fund_invoice__is_deleted=False,
                    acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING)
                acknowledgement_status = models.CREDIT_PAYMENT_ACKNOWLEDGED
                acknowledgement_completed = True
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)

        elif request.user.user_role == settings.SUPPLIER["number_value"]:
            if int(request.data["payment_type"]) == models.PAYMENT_TO_SUPPLIER_BY_ADMIN:
                queryset_filter = models.PaymentModel.objects.filter(
                    payment_made_by__user_role=settings.ADMIN["number_value"],
                    fund_invoice__supplier=request.user,
                    payment_type=int(request.data["payment_type"]),
                    acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGMENT_PENDING,
                    fund_invoice__is_deleted=False)
                acknowledgement_status = models.CREDIT_PAYMENT_ACKNOWLEDGED
                acknowledgement_completed = True
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)
        payment_object = get_object_or_404(queryset_filter, pk=request.data['payment_id'])
        payment_object.acknowledgement_status = acknowledgement_status
        payment_object.acknowledgement_completed = acknowledgement_completed
        payment_object.save()

        # Entering the request data status to PaymentStatusModel Table
        payment_status_data = {"action_taken": models.CREDIT_PAYMENT_RECEIVED_ACKNOWLEDGED,
                               'action_by': request.user.id,
                               "payment": payment_object.id}
        status_serializer_data = serializers.PaymentStatusModelSerializer(data=payment_status_data)
        status_serializer_data.is_valid(raise_exception=True)
        status_serializer_data.save()
        return Response({'message': 'Payment acknowledged successfully!'}, status=status.HTTP_200_OK)


class GenerateDocSign(APIView):
    """
    Class for generating the doc sign url
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, **kwargs):
        if 'fund_invoice' in request.data:
            master_contract = None
            if request.user.user_role == settings.ADMIN['number_value']:
                queryset_filter = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_ADMIN_CREATED,
                                                                         is_deleted=False,
                                                                         assign_to=settings.ADMIN[
                                                                             "name_value"]).exclude(
                    fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                by_sme = False
                contract_doc_type = models.GENERATED_CONTRACT
            elif request.user.user_role == settings.SME['number_value']:
                queryset_filter = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                         is_deleted=False,
                                                                         assign_to=settings.SME[
                                                                             "name_value"]).exclude(
                    fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)
                by_sme = True
                contract_doc_type = models.ADMIN_SIGNED_CONTRACT
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
            fund_invoice_object = get_object_or_404(queryset_filter, pk=request.data['fund_invoice'])
            contract_obj = models.ContractModel.objects.get(fund_invoice=fund_invoice_object)
            envelope_data = docu_sign_make_envelope(request.user.email, request.user.first_name, by_sme,
                                                    contract_obj.id,
                                                    fund_invoice_object.contract_fund_invoice.all()[0].
                                                    signed_contract_file.filter(
                                                        file_status=models.SIGNED_CONTRACT_ADDED,
                                                        contract_doc_type=contract_doc_type)[0].
                                                    file_path, master_contract)
            return Response(envelope_data, status=status.HTTP_200_OK)
        else:
            master_contract = True
            if request.user.user_role == settings.ADMIN['number_value']:
                queryset_filter = models.ContractModel.objects.filter(master_contract_status__action_taken__contains=
                                                                      settings.CREDIT_CONTRACT_ADMIN_CREATED,
                                                                      master_contract_status__assign_to=settings.ADMIN[
                                                                          "name_value"]).exclude(
                    master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                by_sme = False
                contract_doc_type = models.GENERATED_CONTRACT

            elif request.user.user_role == settings.SME['number_value']:
                queryset_filter = models.ContractModel.objects.filter(master_contract_status__action_taken__contains=
                                                                      settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                      master_contract_status__assign_to=settings.SME[
                                                                          "name_value"]).exclude(
                    master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)
                by_sme = True
                contract_doc_type = models.ADMIN_SIGNED_CONTRACT

            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
            contract_object = get_object_or_404(queryset_filter, pk=request.data['contract_id'])
            envelope_data = docu_sign_make_envelope(request.user.email, request.user.first_name, by_sme,
                                                    contract_object.id,
                                                    contract_object.
                                                    signed_contract_file.filter(
                                                        file_status=models.SIGNED_CONTRACT_ADDED,
                                                        contract_doc_type=contract_doc_type)[0].
                                                    file_path, master_contract)
            return Response(envelope_data, status=status.HTTP_200_OK)


class GetSignedDoc(APIView):
    """
    Class for getting signed doc
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, **kwargs):
        if 'fund_invoice' in request.data:
            if request.user.user_role == settings.ADMIN['number_value']:
                queryset_filter = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_ADMIN_CREATED,
                                                                         is_deleted=False,
                                                                         assign_to=settings.ADMIN[
                                                                             "name_value"]).exclude(
                    fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
            elif request.user.user_role == settings.SME['number_value']:
                queryset_filter = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                         is_deleted=False,
                                                                         assign_to=settings.SME[
                                                                             "name_value"]).exclude(
                    fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
            fund_invoice_object = get_object_or_404(queryset_filter, pk=request.data['fund_invoice'])
            sign_doc_data = get_docu_sign_doc(request.data['envelope_id'], request.user, fund_invoice_object)
            # if sign_doc_data['status']:
            #     return Response(sign_doc_data['data'], status=status.HTTP_200_OK)
            # else:
            #     return Response(sign_doc_data['data'], status=status.HTTP_200_OK)
        else:
            if request.user.user_role == settings.ADMIN['number_value']:
                queryset_filter = models.ContractModel.objects.filter(master_contract_status__action_taken__contains=
                                                                      settings.CREDIT_CONTRACT_ADMIN_CREATED,
                                                                      master_contract_status__assign_to=settings.ADMIN[
                                                                          "name_value"]).exclude(
                    master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
            elif request.user.user_role == settings.SME['number_value']:
                queryset_filter = models.ContractModel.objects.filter(master_contract_status__action_taken__contains=
                                                                      settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                      master_contract_status__assign_to=settings.SME[
                                                                          "name_value"]).exclude(
                    master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
            contract_obj = get_object_or_404(queryset_filter, pk=request.data['contract_id'])
            sign_doc_data = get_docu_sign_doc(request.data['envelope_id'], request.user, None,
                                              contract_obj.sme_master_contract)
            # if sign_doc_data['status']:
            #     return Response(sign_doc_data['data'], status=status.HTTP_200_OK)
            # else:
            #     return Response(sign_doc_data['data'], status=status.HTTP_200_OK)
        if sign_doc_data['status']:
            if request.user.user_role == settings.ADMIN['number_value']:
                if "contract_id" in request.data:
                    contract_object = get_object_or_404(models.ContractModel, pk=request.data['contract_id'])
                    assignee = contract_object.sme_master_contract.id
                    status_obj = models.MasterContractStatusModel.objects.filter(
                        action_taken=settings.CREDIT_CONTRACT_ADMIN_CREATED,
                        assign_to=settings.ADMIN[
                            "name_value"], contract=contract_object).exclude(
                        action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                    if status_obj.exists():
                        signed_contract_object = contract_object.signed_contract_file.all().filter(
                            contract_doc_type=models.ADMIN_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_CREATED)
                        if not signed_contract_object.exists():
                            return Response({'data': sign_doc_data['data'],
                                             "detail": "Please finish the contract document signing"},
                                            status=status.HTTP_400_BAD_REQUEST)

                        status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_SIGNED)

                        sme_reminder_mail(settings.SIGN_CONTRACT, contract_object.sme_master_contract.first_name,
                                          contract_object.sme_master_contract.email, contract_object.id)

                        # Entering the request data status to MasterContractStatus Table
                        master_contract_status_data = {"contract": contract_object.id, "action_taken": status_data[0],
                                                       'action_by': request.user.id, "assign_to": status_data[1]}
                        status_serializer_data = serializers.MasterContractStatusSerializers(
                            data=master_contract_status_data)
                    else:
                        return Response({'data': sign_doc_data['data'], 'message': 'Detail not found'},
                                        status=status.HTTP_400_BAD_REQUEST)
                elif "fund_invoice" in request.data:
                    contract_object = get_object_or_404(models.ContractModel, fund_invoice=request.data['fund_invoice'])
                    status_obj = models.FundInvoiceStatusModel.objects.filter(action_taken__contains=
                                                                              settings.CREDIT_CONTRACT_ADMIN_CREATED,
                                                                              fund_invoice__is_deleted=False,
                                                                              fund_invoice=contract_object.fund_invoice,
                                                                              fund_invoice__assign_to=settings.ADMIN[
                                                                                  "name_value"]).exclude(
                        action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                    if status_obj.exists():
                        fund_invoice_object = contract_object.fund_invoice
                    assignee = fund_invoice_object.sme.id
                    signed_contract_object = contract_object.signed_contract_file.all().filter(contract_doc_type=
                                                                                               models.ADMIN_SIGNED_CONTRACT,
                                                                                               file_status=models.SIGNED_CONTRACT_CREATED)
                    if not signed_contract_object.exists():
                        return Response(
                            {'data': sign_doc_data['data'], "detail": "Please finish the contract document signing"},
                            status=status.HTTP_400_BAD_REQUEST)
                    status_data = generate_request_status(settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                    sme_reminder_mail(settings.SIGN_CONTRACT, fund_invoice_object.sme.first_name,
                                      fund_invoice_object.sme.email, contract_object.id)

                    # Updating the FundInvoiceModel Table
                    fund_invoice_object.assign_to = status_data[1]
                    fund_invoice_object.save()
                    # Entering the request data status to FundInvoiceStatusModel Table
                    fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                                'action_by': request.user.id}
                    status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
                else:
                    return Response({'data': sign_doc_data['data'], 'message': 'Detail not found'},
                                    status=status.HTTP_400_BAD_REQUEST)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()

                # Updating signed contract file instance
                signed_contract_object.update(file_status=models.SIGNED_CONTRACT_ADDED, reminder_count=1)
                notification_data = {"contract": contract_object.id,
                                     "notification": "Contract Admin Signed",
                                     "type": settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                     "description": "SME Signing is Pending",
                                     "assignee": assignee
                                     }
                notification_serializer = serializers.NotificationModelSerializer(data=notification_data)
                if notification_serializer.is_valid(raise_exception=True):
                    notification_serializer.save()
                return Response({'data': sign_doc_data['data'], 'message': 'Contract signed by Admin'},
                                status=status.HTTP_200_OK)
            if request.user.user_role == settings.SME['number_value']:
                if "contract_id" in request.data:
                    contract_object = models.ContractModel.objects.get(id=request.data['contract_id'])
                elif "fund_invoice" in request.data:
                    contract_object = models.ContractModel.objects.get(fund_invoice=request.data['fund_invoice'])
                if contract_object.is_master_contract:
                    if not request.user.master_contract == contract_object:
                        return Response(
                            {'data': sign_doc_data['data'], 'message': 'Master contract doesnot belongs to this SME'},
                            status=status.HTTP_200_OK)
                    status_obj = models.MasterContractStatusModel.objects.filter(
                        action_taken=settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                        assign_to=settings.SME[
                            "name_value"],
                        contract=contract_object
                    ).exclude(
                        action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)
                    if status_obj.exists():
                        signed_contract_object = contract_object.signed_contract_file.all().filter(
                            contract_doc_type=models.SME_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_CREATED)
                        if not signed_contract_object.exists():
                            return Response({'data': sign_doc_data['data'],
                                             "detail": "Please finish the contract document signing"},
                                            status=status.HTTP_400_BAD_REQUEST)

                        status_data = generate_request_status(settings.CREDIT_CONTRACT_SME_APPROVED, True)
                        # Entering the request data status to MasterContractStatus Table
                        master_contract_status_data = {"contract": contract_object.id, "action_taken": status_data[0],
                                                       'action_by': request.user.id, "assign_to": status_data[1]}
                        status_serializer_data = serializers.MasterContractStatusSerializers(
                            data=master_contract_status_data)
                    else:
                        return Response({'data': sign_doc_data['data'], 'message': 'Detail not found'},
                                        status=status.HTTP_400_BAD_REQUEST)
                else:
                    status_obj = models.FundInvoiceStatusModel.objects.filter(fund_invoice__sme=request.user,
                                                                              fund_invoice__is_deleted=False,
                                                                              action_taken__contains=
                                                                              settings.CREDIT_CONTRACT_ADMIN_SIGNED,
                                                                              fund_invoice=contract_object.fund_invoice,
                                                                              fund_invoice__assign_to=settings.SME[
                                                                                  "name_value"]).exclude(
                        action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)

                    fund_invoice_object = contract_object.fund_invoice
                    signed_contract_object = contract_object.signed_contract_file.all().filter(
                        contract_doc_type=models.SME_SIGNED_CONTRACT,
                        file_status=models.SIGNED_CONTRACT_CREATED)
                    if not signed_contract_object.exists():
                        return Response(
                            {'data': sign_doc_data['data'], "detail": "Please finish the contract document signing"},
                            status=status.HTTP_400_BAD_REQUEST)

                    status_data = generate_request_status(settings.CREDIT_CONTRACT_SME_APPROVED)

                    # Updating the FundInvoiceModel Table
                    fund_invoice_object.assign_to = status_data[1]
                    fund_invoice_object.save()
                    # Entering the request data status to FundInvoiceStatusModel Table
                    fund_invoice_status_data = {"fund_invoice": fund_invoice_object.id, "action_taken": status_data[0],
                                                'action_by': request.user.id}
                    status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
                    notification_data = {
                        "contract": contract_object.id,
                        "notification": "Contract was Approved by SME",
                        "type": settings.CREDIT_CONTRACT_SME_APPROVED,
                        "description": "Shipment Upload is Pending",
                        "assignee": fund_invoice_object.sme.id
                    }
                    notification_serializer = serializers.NotificationModelSerializer(data=notification_data)
                    if notification_serializer.is_valid(raise_exception=True):
                        notification_serializer.save()
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()

                # Updating signed contract file instance
                signed_contract_object.update(file_status=models.SIGNED_CONTRACT_ADDED)
                notification_obj = models.NotificationModel.objects.filter(contract_id=contract_object.id,
                                                                           type=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                return Response({'data': sign_doc_data['data'], 'message': 'Contract signed by SME'},
                                status=status.HTTP_200_OK)
            else:
                return Response({'Detail': 'You dont have permission to perform this action.'})
        else:
            return Response(sign_doc_data['data'], status=status.HTTP_200_OK)


class PaymentInvoiceListing(APIView):
    """
    Class for listing invoice details for a payment
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        output_arr = []
        if request.user.user_role == settings.SUPPLIER["number_value"]:
            fund_invoice_object = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                         Q(contract_category=
                                                                           settings.MASTER_CONTRACT['number_value']),
                                                                         supplier=request.user,
                                                                         is_deleted=False).distinct()
        elif request.user.user_role == settings.ADMIN["number_value"]:
            fund_invoice_object = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                         Q(contract_category=
                                                                           settings.MASTER_CONTRACT['number_value']),
                                                                         is_deleted=False).distinct()
        elif request.user.user_role == settings.SME["number_value"]:
            fund_invoice_object = models.FundInvoiceModel.objects.filter(Q(fund_invoice_status__action_taken__contains=
                                                                           settings.CREDIT_CONTRACT_SME_APPROVED) |
                                                                         Q(contract_category=
                                                                           settings.MASTER_CONTRACT['number_value']),
                                                                         sme=request.user,
                                                                         is_deleted=False).distinct()
        elif request.user.user_role == settings.FACTOR["number_value"]:
            fund_invoice_object = models.FundInvoiceModel.objects.filter(fund_invoice_status__action_taken__contains=
                                                                         settings.CREDIT_CONTRACT_SME_APPROVED,
                                                                         contract_fund_invoice__factoring_company=
                                                                         request.user, is_deleted=False)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)
        total_invoice_amount = 0
        if fund_invoice_object.exists():
            for invoice in fund_invoice_object:
                output_dict = {"invoice_id": invoice.id, "sme": invoice.sme.on_boarding_details.company_name,
                               "supplier": invoice.supplier.on_boarding_details.company_name,
                               "invoice_amount": invoice.invoice_total_amount,
                               "invoice_date": invoice.invoice_date,
                               "invoice_number": invoice.invoice_number}
                total_invoice_amount += invoice.invoice_total_amount
                output_arr.append(output_dict)
        return Response({'results': output_arr, "total_invoice_amount": total_invoice_amount},
                        status=status.HTTP_200_OK)


class ShipmentFileUpload(APIView):
    """
    Class for uploading additional shipment files
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.user_role == settings.SUPPLIER["number_value"] or \
                request.user.user_role == settings.SME["number_value"]:
            if request.user.user_role == settings.SME["number_value"]:
                shipment_data = get_object_or_404(models.ShipmentModel, id=request.data['shipment_id'],
                                                  fund_invoice__assign_to=settings.SME["name_value"],
                                                  fund_invoice__is_deleted=False)
                if shipment_data.fund_invoice.fund_invoice_status.all()[0].action_taken == \
                        settings.CREDIT_SHIPMENT_SUPPLIER_SEND_BACK:
                    status_data = generate_request_status(settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SME_UPLOADED)
                else:
                    return Response({'message': 'Please check the Selected action!'},
                                    status=status.HTTP_400_BAD_REQUEST)
                notification_obj = models.NotificationModel.objects.filter(shipment_id=shipment_data.id,
                                                                           type=settings.SHIPMENT_SEND_BACK_BY_SUPPLIER)
                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                notification_data = {"shipment": shipment_data.id, "notification": "Additional File Uploaded",
                                     "type": settings.SHIPMENT_ADDITIONAL_FILE_ADDED_BY_SME,
                                     "description": "Shipment Approval is Pending",
                                     "assignee": shipment_data.fund_invoice.supplier.id}


            else:
                status_data = generate_request_status(settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SUPPLIER_UPLOADED)
                shipment_data = get_object_or_404(models.ShipmentModel, id=request.data['shipment_id'],
                                                  fund_invoice__supplier=request.user, fund_invoice__assign_to=
                                                  settings.SUPPLIER["name_value"], fund_invoice__is_deleted=False)
                if shipment_data.fund_invoice.fund_invoice_status.all()[0].action_taken == \
                        settings.CREDIT_SHIPMENT_SME_SEND_BACK:
                    status_data = generate_request_status(settings.CREDIT_SHIPMENT_ADDITIONAL_FILE_SUPPLIER_UPLOADED)
                else:
                    return Response({'message': 'Please check the Selected action!'},
                                    status=status.HTTP_400_BAD_REQUEST)
                notification_obj = models.NotificationModel.objects.filter(shipment_id=shipment_data.id,
                                                                           type=settings.SHIPMENT_SEND_BACK_BY_SME)
                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                notification_data = {"shipment": shipment_data.id, "notification": "Additional file Uploaded",
                                     "type": settings.SHIPMENT_ADDITIONAL_FILE_ADDED_BY_SUPPLIER,
                                     "description": "Shipment Approval is Pending",
                                     "assignee": shipment_data.fund_invoice.sme.id}
            notification_serializer = serializers.NotificationModelSerializer(data=notification_data)
            if notification_serializer.is_valid(raise_exception=True):
                notification_serializer.save()
                # Entering the shipment files to  AdditionalShipmentFilesModel Table
            if 'additional_documents' not in request.FILES:
                return Response({"detail": "Please add at least one file"},
                                status=status.HTTP_400_BAD_REQUEST)
            files_list = list()
            for file_object in request.FILES.getlist('additional_documents'):
                files_list.append(models.AdditionalShipmentFilesModel(shipment=shipment_data,
                                                                      action_by=request.user,
                                                                      additional_shipment_file=file_object))
            models.AdditionalShipmentFilesModel.objects.bulk_create(files_list)

            # Updating the FundInvoiceModel Table
            shipment_data.fund_invoice.assign_to = status_data[1]
            shipment_data.fund_invoice.save()

            # Entering the request data status to FundInvoiceStatusModel Table
            fund_invoice_status_data = {"fund_invoice": shipment_data.fund_invoice.id, "action_taken": status_data[0],
                                        'action_by': request.user.id}
            status_serializer_data = serializers.FundInvoiceStatusModelSerializer(data=fund_invoice_status_data)
            status_serializer_data.is_valid(raise_exception=True)
            status_serializer_data.save()
            return Response({'message': 'Additional Shipment files added Successfully!'},
                            status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class DeleteFundInvoice(APIView):
    """
    Class for Deleting fund invoice
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request, **kwarg):
        fund_invoice_object = get_object_or_404(models.FundInvoiceModel, pk=kwarg['fund_invoice_id'])
        notification_obj = models.NotificationModel.objects.filter(fund_invoice=fund_invoice_object)
        if notification_obj.exists():
            notification_obj.update(is_deleted=True)
        fund_invoice_object.is_deleted = True
        fund_invoice_object.save()

        return Response({"detail": "Successfully deleted the FundInvoice."},
                        status=status.HTTP_200_OK)


class FundInvoiceInfo(APIView):
    """
    Class for listing fund invoice
    """
    permission_classes = [IsCustomAdminUser]

    def get(self, request):
        total_fund_invoice = models.FundInvoiceModel.objects.filter(Q(
            fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED) | Q
                                                                    (contract_category=settings.MASTER_CONTRACT[
                                                                        'number_value'])).distinct(). \
            aggregate(Sum('invoice_total_amount'))
        advance_amount = 0
        supplier_paid_amount = 0
        if not total_fund_invoice['invoice_total_amount__sum'] is None:
            fund_invoice_obj = models.FundInvoiceModel.objects.filter(supplier_term__supplier_terms__before_shipment=
                                                                      True).distinct()
            for fund_invoice in fund_invoice_obj:
                terms = fund_invoice.supplier_term.supplier_terms.filter(before_shipment=True)
                for term in terms:
                    payment_obj = models.PaymentModel.objects.filter(fund_invoice=fund_invoice,
                                                                     payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN,
                                                                     term_order=term.terms_order)
                    if payment_obj.exists():
                        advance_amount += payment_obj.first().paying_amount
            paid_amount = models.PaymentModel.objects.filter(
                Q(fund_invoice__fund_invoice_status__action_taken__contains=
                  settings.CREDIT_CONTRACT_SME_APPROVED) |
                Q(fund_invoice__contract_category=settings.MASTER_CONTRACT['number_value']),
                payment_type=models.PAYMENT_TO_SUPPLIER_BY_ADMIN).distinct(). \
                aggregate(Sum('paying_amount'))
            if paid_amount["paying_amount__sum"] is None:
                balance_to_be_paid = total_fund_invoice['invoice_total_amount__sum']
            else:
                supplier_paid_amount = paid_amount['paying_amount__sum']
                balance_to_be_paid = total_fund_invoice['invoice_total_amount__sum'] - paid_amount['paying_amount__sum']
                if balance_to_be_paid < 0:
                    balance_to_be_paid = 0
        else:
            total_fund_invoice['invoice_total_amount__sum'] = 0
            balance_to_be_paid = 0

        output_dict = {"cards": {"total": total_fund_invoice["invoice_total_amount__sum"],
                                 "advance_payment_amount": advance_amount,
                                 "supplier_paid": supplier_paid_amount,
                                 "balance_to_be_paid": balance_to_be_paid}}

        return Response({"data": output_dict}, status=status.HTTP_200_OK)


class SMEReminderMail(APIView):
    """
    Class for sending reminder mail
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        try:
            contract_object = models.ContractModel.objects.get(id=request.data['contract_id'])
        except User.DoesNotExist:
            return Response({'detail': 'Invalid User Id'}, status=status.HTTP_400_BAD_REQUEST)

        signed_contract_object = contract_object.signed_contract_file.all().filter(
            contract_doc_type=models.ADMIN_SIGNED_CONTRACT, file_status=models.SIGNED_CONTRACT_ADDED)
        # Updating signed contract file instance
        if signed_contract_object.exists():
            signed_contract_object.update(reminder_count=signed_contract_object.first().reminder_count + 1,
                                          reminder_sending_time=datetime.now())
        else:
            return Response({'message': 'Please complete the admin signing'}, status=status.HTTP_200_OK)
        if contract_object.is_master_contract:
            sme_reminder_mail(settings.SIGN_CONTRACT_REMINDER, contract_object.sme_master_contract.first_name,
                              contract_object.sme_master_contract.email, contract_object.id)
        else:
            sme_reminder_mail(settings.SIGN_CONTRACT_REMINDER, contract_object.fund_invoice.sme.first_name,
                              contract_object.fund_invoice.sme.email, contract_object.id)

        return Response({'message': 'Reminder mail send to SME'}, status=status.HTTP_200_OK)


class AccountDetailsViewSet(viewsets.ModelViewSet):
    """
    Class for Create, update, and Retrieve operations on AccountDetailsModel
    """
    queryset = models.AccountDetailsModel.objects.all()
    serializer_class = serializers.AccountDetailsModelSerializer
    permission_classes = [IsCustomAdminUser]
    http_method_names = ['get', 'post', 'put']

    def retrieve(self, request, *args, **kwargs):
        account_object = self.get_queryset().first()
        serializer_data = self.serializer_class(account_object, context={"request": request})
        return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        account_object = self.get_queryset().first()
        serializer_data = self.serializer_class(account_object, request.data, partial=True,
                                                context={"request": request})
        serializer_data.is_valid()
        serializer_data.save()
        return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)


class CityDetailsViewSet(viewsets.ModelViewSet):
    """
    class for retrieve city details while searching
    """
    # permission_classes = [IsAuthenticated]
    queryset = City.objects.all()
    serializer_class = serializers.CitySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', '=id']
    ordering_fields = ['name']
    pagination_class = PageNumberPagination
    pagination_class.page_size = 50

    # def get(self, request):
    #     if request.GET.get('search'):
    #         search_id = None
    #         if request.GET['search'].isnumeric():
    #             search_id = request.GET['search']
    #         queryset = City.objects.filter(Q(id=search_id) | Q(name__icontains=request.GET['search']))[:50]
    #     else:
    #         queryset = City.objects.filter(name__istartswith='A')[:50]
    #     serializer_class = serializers.CitySerializer(queryset, many=True)
    #     return Response(serializer_class.data)


class DeletePaymentTerm(APIView):
    """
    Class for deleting a supplier payment term
    """

    permission_classes = [IsCustomAdminUser]

    def post(self, request, **kwargs):
        term_object = get_object_or_404(models.PaymentTermModel, pk=kwargs['term_id'], is_delete=False)
        if not term_object.for_sme:
            # TODO : check the dependency of fund invoice and supplier term.
            if term_object.invoice_supplier_terms.all().count() == 0:
                term_object.is_delete = True
                term_object.save()
                return Response({'detail': 'Supplier payment term deleted successfully.'},
                                status=status.HTTP_204_NO_CONTENT)
            else:
                return Response({'detail': 'You cant delete the supplier term'})
        else:
            # TODO : check the dependency of contract type and SME payment term.
            if term_object.payment_terms.all().count() == 0:
                term_object.is_delete = True
                term_object.save()
                return Response({'detail': 'SME payment term deleted successfully.'},
                                status=status.HTTP_204_NO_CONTENT)
            else:
                return Response({'detail': 'You cant delete the SME payment term'})


class ContractAdditionalCostTypeViewset(viewsets.ModelViewSet):
    """
    Class for CRUD operation in ContractAdditionalCostType model
    """
    permission_classes = [IsAuthenticated]
    queryset = models.ContractAdditionalCostType.objects.all().order_by('id')
    serializer_class = serializers.ContractAdditionalCostTypeSerializer

    def create(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            if 'additional_cost_type' not in request.data:
                return Response({'detail': 'please add additional_cost_type.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                additional_cost_serializer = self.serializer_class(data=request.data)
                additional_cost_serializer.is_valid(raise_exception=True)
                additional_cost_serializer.save()
                return Response(additional_cost_serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def update(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            additional_cost_data = get_object_or_404(models.ContractAdditionalCostType, pk=kwargs['pk'])
            additional_cost_serializer = self.serializer_class(additional_cost_data, data=request.data)
            additional_cost_serializer.is_valid(raise_exception=True)
            additional_cost_serializer.save()
            return Response({'detail': 'Successfully updated.', 'data': additional_cost_serializer.data},
                            status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class GetNotification(APIView):
    """
    Class for viewing notifications
    """

    def get(self, request, ):
        if request.user.user_role == settings.ADMIN["number_value"]:
            query_set = models.NotificationModel.objects.filter(is_read=False, is_completed=False, assignee=None,
                                                                is_deleted=False).order_by('-id')
        elif request.user.user_role == settings.SUPPLIER["number_value"] or settings.SME["number_value"]:
            query_set = models.NotificationModel.objects.filter(is_read=False, is_completed=False,
                                                                assignee=request.user, is_deleted=False).order_by(
                '-id')
        serializer = serializers.NotificationModelSerializer(query_set, many=True, context={"request": request})
        return Response({'notifications': serializer.data}, status=status.HTTP_200_OK)


class GetContractNumber(APIView):
    """
    Class for getting the autogenerate contract number
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            contract_object = models.ContractModel.objects.latest('id')
        except:
            contract_object = None
        data = get_new_contract_number(contract_object)
        return Response({'Contract_number': data}, status=status.HTTP_200_OK)


class DeleteNotification(APIView):
    """
    Class for deleting a notification
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, **kwargs):
        notification_obj = get_object_or_404(models.NotificationModel, pk=kwargs['notification_id'])
        notification_obj.is_deleted = True
        notification_obj.save()

        return Response({"detail": "Successfully deleted the notifications"},
                        status=status.HTTP_200_OK)


class SupplierShippingDetails(APIView):
    """
    class auto populate the port of origin and discharge from last transaction with same supplier
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        supplier_id = request.GET.get('supplier')
        fund_invoice = models.FundInvoiceModel.objects.filter(sme=request.user,
                                                              supplier_id=supplier_id).order_by('-id').first()
        if fund_invoice:
            country_data = []
            shipping_details = models.FundInvoiceCountryModel.objects.filter(fund_invoice=fund_invoice)
            shipping_data = serializers.FundInvoiceCountryModelSerializer(shipping_details, many=True)
            for data in shipping_data.data:
                country_data.append({'id': data['origin_city'],
                                     'name': data['origin_city_name'],
                                     'display_name': data['origin_display_name'],
                                     'country': data['origin_country_code']})
                country_data.append({'id': data['destination_city'],
                                     'name': data['destination_city_name'],
                                     'display_name': data['destination_display_name'],
                                     'country': data['destination_country_code']})
            return Response({'result': {'data': shipping_data.data, 'country_data': country_data,
                                        'transport_mode': fund_invoice.transport_mode}}, status=status.HTTP_200_OK)
        else:
            return Response({'result': {'data': [], 'transport_mode': None}}, status=status.HTTP_200_OK)


class GetPaymentHistory(APIView):
    """
    Class for getting payment history
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN['number_value'] or kwargs['user_id'] == request.user.id:
            query_set = models.PaymentModel.objects.filter(
                Q(acknowledgement_status=models.CREDIT_PAYMENT_ACKNOWLEDGED) |
                Q(acknowledgement_status=models.CREDIT_PAYMENT_PAID), payment_made_by=kwargs['user_id'])
        else:
            return Response({'details': 'You dont have permission to perform this action.'},
                            status=status.HTTP_400_BAD_REQUEST)
        output_data = serializers.PaymentModelSerializer(query_set, many=True, context={'request': request})
        return Response(output_data.data, status=status.HTTP_200_OK)


class GetPaymentDetails(APIView):
    """
    Class for getting payment details in history
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN['number_value'] or kwargs['user_id'] == request.user.id:
            queryset_filter = models.FundInvoiceModel.objects.filter(is_deleted=False)
            fund_invoice_object = get_object_or_404(queryset_filter, pk=kwargs['fund_invoice_id'])
            output_dict = {"sme": fund_invoice_object.sme.on_boarding_details.company_name,
                           "supplier": fund_invoice_object.supplier.on_boarding_details.company_name,
                           "sme_invoice_number": fund_invoice_object.invoice_number,
                           "supplier_invoice_number": fund_invoice_object.invoice_number
                           }
            return Response({'result': output_dict}, status=status.HTTP_200_OK)


class CalculateOverdueAmount(APIView):
    """
    Class for getting payment history
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        fund_invoice = get_object_or_404(models.FundInvoiceModel, pk=kwargs['fund_invoice'])
        overdue_amount = calculate_overdue_amount(fund_invoice.sme)
        return Response({"overdue_amount": overdue_amount}, status=status.HTTP_200_OK)

# class UploadInvoiceViewSet(viewsets.ModelViewSet):
#     """
#     Class for Create, and Retrieve operations on UserDetailModel
#     """
#     queryset = models.RequestInvoiceModel.objects.all()
#     serializer_class = serializers.RequestInvoiceModelSerializer
#     permission_classes = [IsAuthenticated]
#     pagination_class = PageNumberPagination
#
#     def create(self, request, *args, **kwargs):
#         input_dict = request.POST.copy()
#         invoice_object = self.get_queryset().filter(request_id=input_dict['request_id'])
#         if invoice_object.exists():
#             return Response({
#                 'detail': 'Invoice cannot be added more than once'}, status=status.HTTP_400_BAD_REQUEST)
#
#         if request.user.user_role == settings.SME['number_value']:
#             request_object = get_object_or_404(models.RequestModel, pk=input_dict['request_id'],
#                                                status_stage=settings.CREATE_CREDIT_REQUEST, status_stage_completed=True,
#                                                assign_to=request.user.get_user_role_display())
#             # Checking if the invoice grand_total amount is greater than the credit amount
#             if not float(input_dict["grand_total"]) <= float(request_object.credit_amount):
#                 return Response({'detail': 'Invoice total greater than the credit amount'},
#                                 status=status.HTTP_400_BAD_REQUEST)
#         elif request.user.user_role == settings.SUPPLIER['number_value']:
#             request_object = get_object_or_404(models.RequestModel, pk=input_dict['request_id'],
#                                                status_stage=settings.CREDIT_INVOICE_UPLOAD,
#                                                status_stage_completed=False,
#                                                assign_to=request.user.get_user_role_display())
#         else:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#
#         input_dict["request"] = input_dict['request_id']
#         input_dict["invoice_date"] = datetime.strptime(request.POST['invoice_date'], '%Y-%m-%d').date()
#         input_dict["shipment_date"] = datetime.strptime(request.POST['shipment_date'], '%Y-%m-%d').date()
#         invoice_serializer_data = self.serializer_class(data=input_dict, context={"request": request})
#         invoice_serializer_data.is_valid(raise_exception=True)
#         invoice_data = invoice_serializer_data.save()
#
#         # Entering the request invoice files to InvoiceFilesModel Table
#         invoice_files_list = list()
#         for file_object in request.FILES.getlist('invoice_files'):
#             invoice_files_list.append(models.InvoiceFilesModel(invoice=invoice_data,
#                                                                invoice_file=file_object,
#                                                                invoice_file_path=f'{settings.CREDIT_REQUEST_DATA}/{str(input_dict["request_id"])}/'
#                                                                                  f'{settings.INVOICE_FILES}/'))
#         models.InvoiceFilesModel.objects.bulk_create(invoice_files_list)
#
#         status_data = generate_request_status(settings.CREDIT_INVOICE_UPLOAD, request.user.user_role)
#         # Updating RequestModel
#         request_object.status_stage = settings.CREDIT_INVOICE_UPLOAD
#         request_object.assign_to = status_data[1]
#         request_object.status_stage_completed = status_data[3]
#         request_object.save()
#
#         # Entering the request data status to RequestStatusModel Table
#         request_status_data = {"request": input_dict['request_id'], "status": status_data[2],
#                                "status_stage": status_data[0], 'action_by': request.user.id}
#         if "remarks" in input_dict:
#             request_status_data['remarks'] = input_dict["remarks"]
#         status_serializer_data = serializers.RequestStatusModelSerializer(data=request_status_data)
#         status_serializer_data.is_valid(raise_exception=True)
#         status_serializer_data.save()
#         return Response({'message': 'Invoice added successfully!', 'data': invoice_serializer_data.data},
#                         status=status.HTTP_201_CREATED)
#
#     def retrieve(self, request, *args, **kwargs):
#         if request.user.user_role == settings.ADMIN["number_value"]:
#             serializer_data = self.serializer_class(self.get_object(), context={"request": request})
#             return Response(serializer_data.data, status=status.HTTP_200_OK)
#         else:
#             filter_set = self.get_queryset().filter(
#                 Q(request__sme=request.user.id) | Q(request__supplier=request.user.id))
#             request_data_object = get_object_or_404(filter_set, pk=kwargs['pk'])
#             serializer_data = self.serializer_class(request_data_object, context={"request": request})
#             return Response(serializer_data.data, status=status.HTTP_200_OK)
#
#     def list(self, request, *args, **kwargs):
#         if request.user.user_role == settings.ADMIN["number_value"]:
#             sme = self.request.query_params.get('sme_id')
#             if sme:
#                 page = self.paginate_queryset(self.get_queryset().filter(request__sme=sme, invoice_status=True))
#             else:
#                 page = self.paginate_queryset(self.get_queryset())
#             if page is not None:
#                 serializer = self.serializer_class(page, many=True, context={"request": request})
#                 return self.get_paginated_response(serializer.data)
#         else:
#             page = self.paginate_queryset(
#                 self.get_queryset().filter(Q(request__sme=request.user.id) | Q(request__supplier=request.user.id)))
#             if page is not None:
#                 serializer = self.serializer_class(page, many=True, context={"request": request})
#                 return self.get_paginated_response(serializer.data)

#
# class SendSupplierInvoiceRequestView(APIView):
#     """
#     Class for sending Supplier request to upload invoice
#     """
#     permission_classes = [IsAuthenticated]
#
#     def post(self, request):
#         if request.user.user_role != settings.SME['number_value']:
#             return Response({
#                 'detail': 'Only an SME can make this request'}, status=status.HTTP_400_BAD_REQUEST)
#
#         invoice_object = models.RequestInvoiceModel.objects.filter(request_id=request.data['request_id'])
#         if invoice_object.exists():
#             return Response({
#                 'detail': 'Invoice cannot be added more than once'}, status=status.HTTP_400_BAD_REQUEST)
#
#         request_object = get_object_or_404(models.RequestModel, pk=request.data['request_id'],
#                                            status_stage=settings.CREATE_CREDIT_REQUEST, status_stage_completed=True,
#                                            assign_to=request.user.get_user_role_display())
#
#         # Sending mail to supplier
#         request_supplier_upload_invoice(settings.EMAIL_SUPPLIER_UPLOAD_INVOICE, request_object)
#
#         status_data = generate_request_status(settings.CREDIT_INVOICE_UPLOAD, request.user.user_role,
#                                               settings.CREDIT_INVOICE_REQUEST_SUPPLIER)
#         # # Updating RequestModel
#         request_object.status_stage = status_data[0]
#         request_object.assign_to = status_data[1]
#         request_object.status_stage_completed = status_data[3]
#         request_object.save()
#
#         # Entering the request data status to RequestStatusModel Table
#         request_status_data = {"request": request.data['request_id'], "status": status_data[2],
#                                "status_stage": status_data[0], 'action_by': request.user.id}
#         if "remarks" in request.data:
#             request_status_data['remarks'] = request.data["remarks"]
#         status_serializer_data = serializers.RequestStatusModelSerializer(data=request_status_data)
#         status_serializer_data.is_valid(raise_exception=True)
#         status_serializer_data.save()
#         return Response({'message': 'Request made to supplier to upload an invoice'}, status=status.HTTP_200_OK)
#
#
# class InvoiceApprovalView(APIView):
#     """
#     Class for approving invoice uploaded
#     """
#     permission_classes = [IsAuthenticated]
#
#     def post(self, request, **kwargs):
#         if kwargs['action'] == settings.CREDIT_REQUEST_APPROVED:
#             action_status = True
#         elif kwargs['action'] == settings.CREDIT_REQUEST_REJECTED:
#             action_status = False
#             # Rejection not implemented
#             return Response(status=status.HTTP_404_NOT_FOUND)
#         else:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#
#         if request.user.user_role == settings.SME['number_value']:
#             request_object = get_object_or_404(models.RequestModel, pk=kwargs['request_id'],
#                                                status_stage=settings.CREDIT_INVOICE_UPLOAD, status_stage_completed=True,
#                                                assign_to=request.user.get_user_role_display())
#             # Condition to be added for selecting the action made
#             action_made = settings.CREDIT_INVOICE_SME_APPROVED
#         elif request.user.user_role == settings.SUPPLIER['number_value']:
#             request_object = get_object_or_404(models.RequestModel, pk=kwargs['request_id'],
#                                                status_stage=settings.CREDIT_INVOICE_UPLOAD, status_stage_completed=True,
#                                                assign_to=request.user.get_user_role_display())
#             # Condition to be added for selecting the action made
#             action_made = settings.CREDIT_INVOICE_SUPPLIER_APPROVED
#         elif request.user.user_role == settings.ADMIN['number_value']:
#             queryset_filter = models.RequestModel.objects.filter(status_stage=settings.CREDIT_INVOICE_APPROVAL,
#                                                                  status_stage_completed=False,
#                                                                  assign_to=request.user.get_user_role_display())
#             request_object = get_object_or_404(queryset_filter, pk=kwargs['request_id'])
#             # Condition to be added for selecting the action made
#             action_made = settings.CREDIT_INVOICE_ADMIN_APPROVED
#         else:
#             return Response(status=status.HTTP_404_NOT_FOUND)
#
#         # Update invoice model
#         invoice_object = get_object_or_404(models.RequestInvoiceModel, request__id=kwargs['request_id'])
#         if float(invoice_object.grand_total) > float(request_object.credit_amount):
#             return Response({"detail": "Invoice cannot be approved as grand total is higher than the request credit "
#                                        "amount"}, status=status.HTTP_400_BAD_REQUEST)
#         status_data = generate_request_status(settings.CREDIT_INVOICE_APPROVAL, request.user.user_role, action_made)
#         invoice_object.invoice_status = status_data[3]
#         invoice_object.save()
#
#         # Updating RequestModel
#         request_object.status_stage = status_data[0]
#         request_object.assign_to = status_data[1]
#         request_object.status_stage_completed = status_data[3]
#         request_object.save()
#
#         # Entering the request data status to RequestStatusModel Table
#         request_status_data = {"request": kwargs['request_id'], "status": status_data[2],
#                                "status_stage": status_data[0], 'action_by': request.user.id}
#         if "remarks" in request.data:
#             request_status_data['remarks'] = request.data["remarks"]
#         status_serializer_data = serializers.RequestStatusModelSerializer(data=request_status_data)
#         status_serializer_data.is_valid(raise_exception=True)
#         status_serializer_data.save()
#         return Response({'message': 'Invoice approved'}, status=status.HTTP_200_OK)
