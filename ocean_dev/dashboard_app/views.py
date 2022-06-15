from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from registration.permissions import IsCustomAdminUser
from transaction_app.models import FundInvoiceModel, PaymentModel, PAYMENT_TO_FACTORING_COMPANY_BY_SME, \
    PAYMENT_TO_SUPPLIER_BY_ADMIN
from contact_app.models import LeadsModel, ON_BOARDING_LEAD, ON_BOARDING_CUSTOMER
from transaction_app import models as transaction_app_models
import datetime
from utils.utility import get_user_available_amount
from registration import models as registration_models

User = get_user_model()


# class DashboardYearlyLeadsInfo(APIView):
#     """
#     Class for getting the count of users based on current status
#     """
#     permission_classes = [IsCustomAdminUser]
#
#     def get(self, request):
#         leads_object = LeadsModel.objects.filter(role=settings.SME_ROLE_VALUE)
#         key_names = ['no_of_leads', 'no_of_opportunities', 'no_of_prospects', 'no_of_onboarded_customers']
#         leads_key = {'no_of_leads': ON_BOARDING_LEAD, 'no_of_opportunities': ON_BOARDING_OPPORTUNITY,
#                      'no_of_prospects': ON_BOARDING_PROSPECT, 'no_of_onboarded_customers': ON_BOARDING_CUSTOMER}
#         output_data = []
#         if leads_object.exists():
#             for yr in range(leads_object[0].submitted_date.year,
#                             leads_object[len(leads_object) - 1].submitted_date.year - 1, -1):
#                 leads_info_data = []
#                 for key_name in key_names:
#                     monthly_leads_count = []
#                     monthly_leads_data = {'name': key_name}
#                     for mnth in range(1, 13):
#                         monthly_leads_count.append(leads_object.filter(submitted_date__year=yr,
#                                                                        submitted_date__month=mnth,
#                                                                        is_deleted=False,
#                                                                        current_status=leads_key[key_name]).count())
#                     monthly_leads_data['data'] = monthly_leads_count
#                     leads_info_data.append(monthly_leads_data)
#                 yearly_data = {'year': yr, 'data': leads_info_data}
#                 output_data.append(yearly_data)
#
#         return Response({"result": output_data}, status=status.HTTP_200_OK)


class DashboardFundsInfo(APIView):
    """
    Class for getting the total amount of payments paid to supplier and payments paid by sme
    """
    permission_classes = [IsCustomAdminUser]

    def get(self, request):
        supplier_payment_object = transaction_app_models.PaymentModel.objects.filter(
            payment_type=transaction_app_models.PAYMENT_TO_SUPPLIER_BY_ADMIN).aggregate(Sum("paying_amount"))
        payment_object = transaction_app_models.PaymentModel.objects.filter(
            payment_type=transaction_app_models.PAYMENT_TO_FACTORING_COMPANY_BY_SME).aggregate(Sum("paying_amount"))
        output_dict = dict()
        if supplier_payment_object['paying_amount__sum']:
            output_dict['supplier_paid'] = supplier_payment_object["paying_amount__sum"]
        else:
            output_dict['supplier_paid'] = 0
        if payment_object['paying_amount__sum']:
            output_dict['funds_received'] = payment_object["paying_amount__sum"]
        else:
            output_dict['funds_received'] = 0
        return Response({"data": output_dict}, status=status.HTTP_200_OK)


# class DashboardYearlyFundsInfo(APIView):
#     """
#     Class for getting the monthly count of invoices
#     """
#     permission_classes = [IsCustomAdminUser]
#
#     def get(self, request):
#         invoice_object = transaction_app_models.FundInvoiceModel.objects.filter(
#             is_deleted=False,
#             fund_invoice_status__action_taken__contains=settings.CREDIT_REQUEST_ADMIN_APPROVED)
#         obj_key = {'invoice_object': 'total_invoices_funded'}
#         output_data = {}
#         monthly_funds_count = []
#         total = 0
#         percent = 0
#         if invoice_object.exists():
#             start_year = invoice_object[0].date_created.year
#             end_year = invoice_object[len(invoice_object) - 1].date_created.year - 1
#         else:
#             start_year = timezone.now().date().year
#             end_year = start_year - 1
#         for yr in range(start_year, end_year, -1):
#             for obj in obj_key:
#                 for mnth in range(1, datetime.date.today().month + 1):
#                     invoices = invoice_object.filter(date_created__year=yr, date_created__month=mnth).count()
#                     if invoices:
#                         monthly_funds_count.append(invoices)
#                         total += invoices
#                     else:
#                         monthly_funds_count.append(0)
#                     if not monthly_funds_count and monthly_funds_count[-2]:
#                         percent = ((monthly_funds_count[-1] - monthly_funds_count[-2]) / monthly_funds_count[-2]) * 100
#             output_data = {'data': monthly_funds_count, 'total': total, 'percent': percent}
#
#         return Response({"result": output_data}, status=status.HTTP_200_OK)


class DashboardTransactionsInfo(APIView):
    """
    Class for getting the pending transaction details
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request, date_created=None):
        required_data = ['to_date', 'from_date']
        for item in required_data:
            if item not in request.data:
                return Response({
                    f"{item}": [
                        "This field is required."
                    ]
                }, status=status.HTTP_400_BAD_REQUEST)
        # current_date = datetime.date.today()
        # last_x_days = current_date - datetime.timedelta(days=int(request.data["time_period"]))
        to_date = request.data['to_date']
        from_date = request.data['from_date']
        user_obj = User.objects.all()
        kyc_pending = 0
        if user_obj.exists():
            kyc_pending = user_obj.filter(on_board_status=registration_models.ON_BOARD_IN_PROGRESS,
                                          is_deleted=False, on_boarding_details__date_created__lte=to_date,
                                          on_boarding_details__date_created__gte=from_date,
                                          user_role=settings.SME["number_value"]).count()
        output_data = {'kyc_pending': kyc_pending,
                       'contracts_pending_approval': transaction_app_models.ContractModel.objects.filter(
                           Q(fund_invoice__is_deleted=False, fund_invoice__fund_invoice_status__action_taken__contains=
                           settings.CREDIT_CONTRACT_ADMIN_SIGNED) | Q(is_master_contract=True,
                                                                      master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_ADMIN_SIGNED)
                           , date_created__gte=from_date,
                           date_created__lte=to_date).exclude(Q(
                           fund_invoice__fund_invoice_status__action_taken__contains=
                           settings.CREDIT_CONTRACT_SME_APPROVED) | Q(
                           master_contract_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED)).
                           count(),
                       'under_production': transaction_app_models.FundInvoiceModel.objects.filter(
                           Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED) |
                           Q(fund_invoice_status__action_taken__contains=
                             settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED), is_deleted=False,
                           date_created__gte=from_date,
                           date_created__lte=to_date).count(),
                       'shipment_pending_approval': transaction_app_models.FundInvoiceModel.objects.filter(
                           Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_CREATED) |
                           Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_CREATED),
                           is_deleted=False, date_created__gte=from_date,
                           date_created__lte=to_date).exclude(
                           Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_ACKNOWLEDGED) |
                           Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_ACKNOWLEDGED)
                       ).count()}

        return Response({"data": output_data}, status=status.HTTP_200_OK)


class DashboardLeadsConversionInfo(APIView):
    """
    Class for getting the count of onboarded users
    """
    permission_classes = [IsCustomAdminUser]

    def get(self, request):
        leads_object = LeadsModel.objects.all()
        output_data = dict()
        key_names = ['no_of_leads', 'no_of_onboarded_customers']
        leads_key = {'no_of_leads': ON_BOARDING_LEAD, 'no_of_onboarded_customers': ON_BOARDING_CUSTOMER}

        if leads_object.exists():
            leads_count = []
            total = 0
            for key_name in key_names:
                leads_count.append(leads_object.filter(is_deleted=False, current_status=leads_key[key_name]).count())
            for count in leads_count:
                total += count

            output_data['label'] = ['leads', 'customers']
            output_data['count'] = leads_count
            output_data['total'] = total

        return Response({"data": output_data}, status=status.HTTP_200_OK)


class DashboardSmeInfo(APIView):
    """
    Class for getting details of the sme
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_role == settings.SME["number_value"]:
            user_object = get_object_or_404(User, pk=request.user.id)
            total_credit_limit = user_object.credit_limit
            available_credit = get_user_available_amount(user_object.id)
            used_credit = user_object.credit_limit - available_credit
            invoice_amount = FundInvoiceModel.objects.filter(sme=user_object.id, is_deleted=False).aggregate(Sum('invoice_total_amount'))
            sme_paid = PaymentModel.objects.filter(payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                   fund_invoice__sme=user_object.id).aggregate(Sum('paying_amount'))
            repayment_amount = invoice_amount['invoice_total_amount__sum'] - sme_paid['paying_amount__sum']
            output_dict = {
                "data": {"cards": {"total_credit_limit": total_credit_limit, "available": available_credit,
                                   "used": used_credit, "repayment_amount": repayment_amount,
                                   "total_invoice_number": FundInvoiceModel.objects.filter(sme=user_object.id,
                                                                                           is_deleted=False).count()},
                         "pieChart": [(available_credit / total_credit_limit) * 100,
                                      (used_credit / total_credit_limit) * 100]}}

            return Response(output_dict, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class AdminDashboardinfo(APIView):
    """
        Class for getting details of the sme cards
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        from_date = request.data.get("from_date")
        to_date = request.data.get("to_date")
        if to_date and from_date:
            sme_user_list = User.objects.filter(user_role=settings.SME["number_value"], is_deleted=False,
                                                date_created__gte=from_date, date_created__lte=to_date)
        available_credit_sme = 0
        if sme_user_list.exists:
            total_credit = sme_user_list.aggregate(Sum('credit_limit')).get('credit_limit__sum') or 0
            if total_credit >= 0:
                for sme_user in sme_user_list:
                    available_credit_sme += get_user_available_amount(sme_user.id)
                used_credit_sme = total_credit - available_credit_sme
            else:
                available_credit_sme = 0
                used_credit_sme = 0
        output_dict = {
            "data": {"cards": {"total_credit_sme": total_credit,
                               "used": used_credit_sme, "balance": available_credit_sme,
                               "total_no_sme": sme_user_list.count()}}}
        return Response(output_dict, status=status.HTTP_200_OK)


class DashboardSmePaymentInfo(APIView):
    """
    Class for getting details of the sme's payment data
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_role == settings.SME["number_value"]:
            result_list = list()
            current_year = datetime.date.today().year
            from_2_years = current_year - 2
            for year in range(current_year, from_2_years, -1):
                sum_metrics = {
                    'total_payment': Sum('paying_amount')
                }
                payment_queryset = PaymentModel.objects.filter(payment_type=PAYMENT_TO_FACTORING_COMPANY_BY_SME,
                                                               fund_invoice__sme=request.user,
                                                               date_created__year=year,
                                                               fund_invoice__is_deleted=False). \
                    values('date_created__month').annotate(**sum_metrics).order_by('date_created__month')
                year_data_array = [0] * 12
                for payment_data in payment_queryset:
                    year_data_array[payment_data['date_created__month'] - 1] = payment_data['total_payment']
                output_data = {"year": year, "data": [{"name": "payment_amount",
                                                       "data": year_data_array}]}
                result_list.append(output_data)
            return Response({"result": result_list}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class DashboardInvoiceRequestOverview(APIView):
    """
    Class for getting the total percentage of invoices requested, approved, pending approval
    """
    permission_classes = [IsCustomAdminUser]

    def get(self, request):
        output_data = dict()
        total_invoice_amount = transaction_app_models.FundInvoiceModel.objects.filter(
            is_deleted=False,
            fund_invoice_status__action_taken__contains=settings.CREDIT_REQUEST_CREATED). \
            aggregate(Sum('invoice_total_amount'))
        invoices_amount_approved = transaction_app_models.FundInvoiceModel.objects.filter(
            is_deleted=False,
            fund_invoice_status__action_taken__contains=settings.CREDIT_REQUEST_ADMIN_APPROVED). \
            aggregate(Sum('invoice_total_amount'))

        if not invoices_amount_approved['invoice_total_amount__sum']:
            invoices_amount_approved['invoice_total_amount__sum'] = 0
        if not total_invoice_amount['invoice_total_amount__sum']:
            total_invoice_amount['invoice_total_amount__sum'] = 0
        invoice_amount_pending = total_invoice_amount["invoice_total_amount__sum"] - \
                                 invoices_amount_approved["invoice_total_amount__sum"]
        total_credit_limit = User.objects.filter().aggregate(Sum('credit_limit'))

        if total_credit_limit["credit_limit__sum"]:
            percent_requested_invoice_amt = (total_invoice_amount['invoice_total_amount__sum'] /
                                             total_credit_limit["credit_limit__sum"]) * 100
            percent_approved_invoice_amt = (invoices_amount_approved['invoice_total_amount__sum'] /
                                            total_credit_limit["credit_limit__sum"]) * 100
            percent_pending_amt = (invoice_amount_pending / total_credit_limit['credit_limit__sum']) * 100
        else:
            percent_requested_invoice_amt = 0
            percent_approved_invoice_amt = 0
            percent_pending_amt = 0

        output_data['label'] = ['Requested', 'Pending Approval', 'Approved']
        output_data['percent'] = [round(percent_requested_invoice_amt, 2), round(percent_pending_amt, 2),
                                  round(percent_approved_invoice_amt, 2)]
        output_data['total'] = round(total_credit_limit["credit_limit__sum"], 2)
        return Response({"data": output_data}, status=status.HTTP_200_OK)


class DashboardSupplierPaymentInfo(APIView):
    """
    Class for getting payment details of the supplier
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_role == settings.SUPPLIER["number_value"]:
            total_invoice_amount_data = transaction_app_models.FundInvoiceModel.objects.filter(
                supplier_id=request.user.id,
                is_deleted=False)
            total_invoice_amount = total_invoice_amount_data.filter(
                Q(contract_category=transaction_app_models.NEW_CONTRACT,
                  fund_invoice_status__action_taken__contains=settings.CREDIT_CONTRACT_SME_APPROVED) |
                Q(contract_category=transaction_app_models.MASTER_CONTRACT,
                  fund_invoice_status__action_taken__contains=settings.CREDIT_REQUEST_ADMIN_APPROVED)). \
                aggregate(Sum('invoice_total_amount'))
            pending_shipment_count = transaction_app_models.FundInvoiceModel.objects.filter(supplier_id=request.user.id,
                                                                                            is_deleted=False). \
                exclude(Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SUPPLIER_CREATED) |
                        Q(fund_invoice_status__action_taken__contains=settings.CREDIT_SHIPMENT_SME_CREATED)).count()

            paid_amount = transaction_app_models.PaymentModel.objects.filter(
                fund_invoice_id__supplier=request.user.id,
                fund_invoice__is_deleted=False,
                payment_type=transaction_app_models.PAYMENT_TO_SUPPLIER_BY_ADMIN). \
                aggregate(Sum('paying_amount'))
            if paid_amount['paying_amount__sum'] is None:
                paid_amount['paying_amount__sum'] = 0
            if total_invoice_amount['invoice_total_amount__sum'] is None:
                percent_amount_paid = 0
                amount_pending = 0
                percent_amount_pending = 0
            else:
                percent_amount_paid = round(paid_amount['paying_amount__sum'] / total_invoice_amount[
                    'invoice_total_amount__sum'] * 100, 2)
                amount_pending = (total_invoice_amount['invoice_total_amount__sum'] -
                                  paid_amount['paying_amount__sum'])
                # if paying amount is greater than invoice amount sets pending amount to be zero
                if amount_pending < 0:
                    amount_pending = 0
                    percent_amount_paid = 100
                percent_amount_pending = round(amount_pending / total_invoice_amount['invoice_total_amount__sum'] * 100,
                                               2)

            output_dict = {"cards": {"total_fund_invoice": total_invoice_amount["invoice_total_amount__sum"],
                                     "pending_amount": amount_pending,
                                     "shipment_pending_count": pending_shipment_count,
                                     "paid_amount": paid_amount["paying_amount__sum"]},
                           "pieChart": [percent_amount_pending, percent_amount_paid]}
            return Response({"data": output_dict}, status=status.HTTP_200_OK)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class DashboardSupplierToPaymentInfo(APIView):
    """
    Class for getting details of the payment data received by the supplier
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_role == settings.SUPPLIER["number_value"]:
            result_list = list()
            current_year = datetime.date.today().year
            from_2_years = current_year - 2
            for year in range(current_year, from_2_years, -1):
                sum_metrics = {
                    'total_payment': Sum('paying_amount')
                }
                payment_queryset = PaymentModel.objects.filter(payment_type=PAYMENT_TO_SUPPLIER_BY_ADMIN,
                                                               fund_invoice__supplier=request.user,
                                                               date_created__year=year,
                                                               fund_invoice__is_deleted=False). \
                    values('date_created__month').annotate(**sum_metrics).order_by('date_created__month')
                year_data_array = [0] * 12
                for payment_data in payment_queryset:
                    year_data_array[payment_data['date_created__month'] - 1] = payment_data['total_payment']
                output_data = {"year": year, "data": [{"name": "payment_amount",
                                                       "data": year_data_array}]}
                result_list.append(output_data)
            return Response({"result": result_list}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)
