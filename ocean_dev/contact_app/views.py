import django_filters.rest_framework
from django.db.models import Sum
from pycountry import currencies
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from django_countries import countries
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db.utils import IntegrityError
from django.contrib.auth import get_user_model
from registration.serializers import UserModelSerializers
from transaction_app.models import NotificationModel
from transaction_app.serializers import NotificationModelSerializer
from registration.permissions import IsCustomAdminUser
from .permissions import IsAdminOrCreateOnly
from . import models
from registration.models import User,UserDetailModel
from registration.serializers import UserModelSerializers
from .serializers import LeadsModelSerializers, ContactModelSerializers, LeadStatusModelSerializers
from utils.utility import create_user, contact_info_send_email, codat_company_creation, delete_codat_company

User = get_user_model()


class LeadsViewSet(ModelViewSet):
    """
    Class for Create, List and Retrieve operations in LeadsModel
    """
    permission_classes = [IsAdminOrCreateOnly]
    queryset = models.LeadsModel.objects.all()
    serializer_class = LeadsModelSerializers
    pagination_class = PageNumberPagination
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['first_name', 'company_email', 'role', 'current_status']
    http_method_names = ['get', 'post', 'put']

    def create(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.user_role == settings.ADMIN["number_value"]:
                if request.data["role"] not in [settings.SME["number_value"], settings.SUPPLIER["number_value"],
                                                settings.FACTOR["number_value"]]:
                    return Response({'detail': 'Please check the role value entered'},
                                    status=status.HTTP_400_BAD_REQUEST)
                if request.data["role"] == settings.FACTOR["number_value"]:
                    request.data['user_role'] = request.data["role"]
                    request.data['email'] = request.data["company_email"]
                    request.data['phone_number'] = request.data['phone_number']
                    user_serializer_data = UserModelSerializers(data=request.data, context={"request": request})
                    if user_serializer_data.is_valid():
                        user_serializer_data.save()
                    else:
                        if "email" in user_serializer_data.errors:
                            return Response({'detail': user_serializer_data.errors['email'][0]},
                                            status=status.HTTP_400_BAD_REQUEST)
                        elif "phone_number" in user_serializer_data.errors:
                            return Response({'Detail': user_serializer_data.errors['phone_number'][0]},
                                            status=status.HTTP_400_BAD_REQUEST)

                        else:
                            return Response(user_serializer_data.errors, status=status.HTTP_400_BAD_REQUEST)

                    return Response(user_serializer_data.data, status=status.HTTP_201_CREATED)
                else:
                    input_dict = request.data
                    if request.data["role"] == settings.SME["number_value"]:
                        if "invoice_amount" not in request.data:
                            return Response({"detail": "Please provide invoice_amount."},
                                            status=status.HTTP_400_BAD_REQUEST)
                        else:
                            if int(request.data["invoice_amount"]) <= 0:
                                return Response({"detail": "Invoice amount should be greater than zero."},
                                                status=status.HTTP_400_BAD_REQUEST)
                            else:
                                input_dict["invoice_amount"] = request.data["invoice_amount"]
                    input_dict['current_status'] = models.ON_BOARDING_CUSTOMER
                    input_dict['sign_up_email'] = input_dict["company_email"]
                    input_dict['sign_up_phone_number'] = input_dict['phone_number']
                    input_dict['created_by'] = request.user.id
                    if input_dict['company_name'] and request.data["role"] == settings.SME["number_value"]:
                        codat_obj = codat_company_creation(input_dict['company_name'])
                        if codat_obj.get('id'):
                            input_dict['company_id'] = codat_obj.get('id')
                    serializer_data = self.serializer_class(data=input_dict)
                    if serializer_data.is_valid():
                        lead_object = serializer_data.save()
                    else:

                        if "sign_up_email" in serializer_data.errors:
                            return Response({'detail': serializer_data.errors['sign_up_email'][0]},
                                            status=status.HTTP_400_BAD_REQUEST)
                        elif "sign_up_phone_number" in serializer_data.errors:
                            return Response({'detail': serializer_data.errors['sign_up_phone_number'][0]},
                                            status=status.HTTP_400_BAD_REQUEST)
                        else:
                            return Response(serializer_data.errors, status=status.HTTP_400_BAD_REQUEST)

                    # Entering the leads data status to LeadStatusModel Table
                    lead_status_data = {"lead": lead_object.id, "status": models.ON_BOARDING_CUSTOMER,
                                        'action_by': request.user.id}
                    if "remarks" in request.data:
                        lead_status_data['remarks'] = request.data["remarks"]
                    status_serializer_data = LeadStatusModelSerializers(data=lead_status_data)
                    status_serializer_data.is_valid(raise_exception=True)
                    status_serializer_data.save()
                    create_user(lead_object)
                    return Response(serializer_data.data, status=status.HTTP_201_CREATED)
            elif request.user.user_role == settings.SME["number_value"]:
                if not request.data['role'] == settings.SUPPLIER["number_value"]:
                    return Response({"message": "User only have the permission to create a supplier"},
                                    status=status.HTTP_400_BAD_REQUEST)
                input_dict = request.data
                input_dict['current_status'] = models.ON_BOARDING_CUSTOMER
                input_dict['created_by'] = request.user.id
                input_dict['sign_up_email'] = input_dict["company_email"]
                input_dict['sign_up_phone_number'] = input_dict["phone_number"]
                if input_dict['company_name'] and request.data["role"] == settings.SME["number_value"]:
                    codat_obj = codat_company_creation(input_dict['company_name'])
                    if codat_obj.get('id'):
                        input_dict['company_id'] = codat_obj.get('id')
                serializer_data = self.serializer_class(data=input_dict)

                if serializer_data.is_valid():
                    lead_object = serializer_data.save()
                else:
                    if "sign_up_email" in serializer_data.errors:
                        return Response({'detail': serializer_data.errors['sign_up_email'][0]},
                                        status=status.HTTP_400_BAD_REQUEST)
                    elif "sign_up_phone_number" in serializer_data.errors:
                        return Response({'Detail': serializer_data.errors['sign_up_phone_number'][0]},
                                        status=status.HTTP_400_BAD_REQUEST)
                    else:
                        return Response(serializer_data.errors, status=status.HTTP_400_BAD_REQUEST)

                # Entering the leads data status to LeadStatusModel Table
                lead_status_data = {"lead": lead_object.id, "status": models.ON_BOARDING_CUSTOMER,
                                    'action_by': request.user.id}
                if "remarks" in request.data:
                    lead_status_data['remarks'] = request.data["remarks"]
                status_serializer_data = LeadStatusModelSerializers(data=lead_status_data)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()
                create_user(lead_object)
                return Response(serializer_data.data, status=status.HTTP_201_CREATED)
            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
        else:
            if request.data["role"] not in [settings.SME["number_value"], settings.SUPPLIER["number_value"]]:
                return Response({'detail': 'Please check the role value entered'},
                                status=status.HTTP_400_BAD_REQUEST)
            input_dict = request.data
            if request.data["role"] == settings.SME["number_value"]:
                if "invoice_amount" not in request.data:
                    return Response({"detail": "Please provide invoice_amount."}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    if int(request.data["invoice_amount"]) <= 0:
                        return Response({"detail": "Invoice amount should be greater than zero."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    else:
                        input_dict["invoice_amount"] = request.data["invoice_amount"]
            input_dict['sign_up_email'] = input_dict["company_email"]
            input_dict['sign_up_phone_number'] = input_dict["phone_number"]
            input_dict['current_status'] = models.ON_BOARDING_LEAD
            if input_dict['company_name'] and request.data["role"] == settings.SME["number_value"]:
                codat_obj = codat_company_creation(input_dict['company_name'])
                if codat_obj.get('id'):
                    input_dict['company_id'] = codat_obj.get('id')
            serializer_data = self.serializer_class(data=input_dict)
            if serializer_data.is_valid():
                serializer_data.save()
            else:
                if "sign_up_email" in serializer_data.errors:
                    return Response({'detail': serializer_data.errors['sign_up_email'][0]},
                                    status=status.HTTP_400_BAD_REQUEST)
                elif "sign_up_phone_number" in serializer_data.errors:
                    return Response({'detail': serializer_data.errors['sign_up_phone_number'][0]},
                                    status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response(serializer_data.errors, status=status.HTTP_400_BAD_REQUEST)
            notification_data = {"lead_user": serializer_data.data["id"], "notification": "A Lead was Created",
                                 "type": settings.LEAD_APPROVAL_PENDING,
                                 "description": "Lead Approval is Pending"}
            notification_serializer = NotificationModelSerializer(data=notification_data)

            if notification_serializer.is_valid(raise_exception=True):
                notification_serializer.save()
            return Response(serializer_data.data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        self.pagination_class.page_size = 1000
        # from_date = request.GET.get("from_date")
        # to_date = request.GET.get("to_date")
        queryset_data = self.get_queryset().filter(is_deleted=False, current_status=models.ON_BOARDING_LEAD)
        # if to_date and from_date:
        #     user_object = list(UserDetailModel.objects.filter(date_created__lte=to_date, date_created__gte=from_date,
        #                                                       company_details__is_active=True). \
        #                        values_list("company_details__email", flat=True))
        #     queryset_data = queryset_data.filter(sign_up_email__in=user_object)
        # if request.GET.get("kyc_pending"):
        #     queryset_data = queryset_data.filter(current_status=models.ON_BOARDING_CUSTOMER, )
        page = self.paginate_queryset(queryset_data)
        total_amount_requested = self.queryset.aggregate(Sum("invoice_amount"))
        if page is not None:
            serializer = self.serializer_class(page, many=True, context={"request": request})
            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data['total_amount_requested'] = total_amount_requested['invoice_amount__sum']
            return paginated_response

    def retrieve(self, request, *args, **kwargs):
        queryset_filter = self.get_queryset().filter(is_deleted=False)
        invoice_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
        serializer_data = self.serializer_class(invoice_object, context={"request": request})
        return Response({'data': serializer_data.data}, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = self.get_queryset().filter(is_deleted=False)
            leads_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])

            input_dict = request.data
            if not input_dict['role'] == leads_object.role:
                if input_dict['role'] == settings.SME["number_value"]:
                    codat_obj = codat_company_creation(input_dict['company_name'])
                    if codat_obj.get('id'):
                            input_dict['company_id'] = codat_obj.get('id')
                elif input_dict['role'] == settings.SUPPLIER["number_value"]: 
                    if leads_object.company_id is not None:
                        delete_response = delete_codat_company(leads_object.company_id)     
                        input_dict['company_id'] = None
            if input_dict['role'] == settings.SME["number_value"]:

                if not leads_object.invoice_amount and "invoice_amount" not in request.data:
                    return Response({"detail": "Please provide invoice_amount."}, status=status.HTTP_400_BAD_REQUEST)
                elif "invoice_amount" in request.data:
                    if int(request.data["invoice_amount"]) <= 0:
                        return Response({"detail": "Invoice amount should be greater than zero."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    else:
                        input_dict["invoice_amount"] = request.data["invoice_amount"]        
            # user_dict = {}
            input_dict['sign_up_email'] = input_dict["company_email"]
            input_dict['sign_up_phone_number'] = input_dict['phone_number']
            # if leads_object.sign_up_email != input_dict["company_email"]:
            #     user_dict['email'] = input_dict["company_email"]
            # if leads_object.sign_up_phone_number != input_dict['phone_number']:
            #     user_dict['phone_number'] = input_dict['phone_number']
            # if leads_object.first_name != input_dict['first_name']:
            #     user_dict['first_name'] = input_dict['first_name']
            # if leads_object.last_name != input_dict['last_name']:
            #     user_dict['last_name'] = input_dict['last_name']
            old_email = leads_object.sign_up_email
            serializer_data = self.serializer_class(leads_object, data=input_dict, partial=True,
                                                    context={"request": request})
            serializer_data.is_valid(raise_exception=True)
            serializer_data.save()

            # # Entering the leads data status to LeadStatusModel Table
            # lead_status_data = {"lead": lead_object.id, "status": models.ON_BOARDING_CUSTOMER,
            #                     'action_by': request.user.id}
            if "remarks" in request.data:
                lead_status_data = {'remarks': request.data["remarks"]}
                lead_status = models.LeadStatusModel.objects.get(id=leads_object.id)
                status_serializer_data = LeadStatusModelSerializers(lead_status, data=lead_status_data, partial=True)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()
            # if user_dict:
            #     user_obj = User.objects.get(email=old_email)
            #     user_serializer = UserModelSerializers(user_obj, data=user_dict, partial=True,
            #                                            context={"request": request})
            #     user_serializer.is_valid(raise_exception=True)
            #     user_serializer.save()
            return Response(serializer_data.data, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class ApproveLeadStatusView(APIView):
    """
    Class for updating status of leads data and also for creating a user
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request, *args, **kwargs):
        lead_object = get_object_or_404(models.LeadsModel, pk=request.data['id'])
        if kwargs['admin_action'] == settings.CREDIT_REQUEST_APPROVED:
            if lead_object.current_status == models.ON_BOARDING_LEAD:

                # lead_object.current_status = models.ON_BOARDING_CUSTOMER
                # lead_object.save()
                #     # Entering the leads data status to LeadStatusModel Table
                #     lead_status_data = {"lead": lead_object.id, "status": models.ON_BOARDING_OPPORTUNITY,
                #                         'action_by': request.user.id}
                #     if "remarks" in request.data:
                #         lead_status_data['remarks'] = request.data["remarks"]
                #     status_serializer_data = LeadStatusModelSerializers(data=lead_status_data)
                #     status_serializer_data.is_valid(raise_exception=True)
                #     status_serializer_data.save()
                #     return Response({"message": f"Lead data's status updated to Opportunity"},
                #                     status=status.HTTP_200_OK)
                #
                # elif lead_object.current_status == models.ON_BOARDING_OPPORTUNITY:
                if 'alternate_email' in request.data and request.data['alternate_email'] is not None:
                    alternate_email = request.data['alternate_email']
                    lead_object.alternate_email = alternate_email
                    lead_object.sign_up_email = alternate_email

                if 'alternate_phone_number' in request.data and request.data['alternate_phone_number'] is not None:
                    alternate_phone_number = request.data['alternate_phone_number']
                    lead_object.alternate_phone_number = alternate_phone_number
                    lead_object.sign_up_phone_number = alternate_phone_number
                else:
                    alternate_phone_number = None
                lead_object.current_status = models.ON_BOARDING_CUSTOMER
                try:
                    lead_object.save()
                except IntegrityError as e:
                    if 'phone_number' in str(e):
                        return Response({'detail': 'Phone number entered already exists'},
                                        status=status.HTTP_400_BAD_REQUEST)
                    else:
                        return Response({'detail': 'Email entered already exists'},
                                        status=status.HTTP_400_BAD_REQUEST)
                # Entering the leads data status to LeadStatusModel Table
                lead_status_data = {"lead": lead_object.id, "status": models.ON_BOARDING_CUSTOMER,
                                    'action_by': request.user.id}
                if "remarks" in request.data:
                    lead_status_data['remarks'] = request.data["remarks"]
                status_serializer_data = LeadStatusModelSerializers(data=lead_status_data)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()
                create_user(lead_object, alternate_phone_number)
                notification_obj = NotificationModel.objects.filter(lead_user_id=lead_object.id)
                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                return Response({"message": "Successfully sent the registration link to the user"},
                                status=status.HTTP_200_OK)
            else:
                return Response({"detail": "Please check the id of the lead entered"},
                                status=status.HTTP_400_BAD_REQUEST)
        elif kwargs['admin_action'] == settings.CREDIT_REQUEST_REJECTED:
            if lead_object.current_status == models.ON_BOARDING_LEAD:
                lead_object.current_status = models.ON_BOARDING_REJECTED
                lead_object.save()
                lead_status_data = {"lead": lead_object.id, "status": models.ON_BOARDING_REJECTED,
                                    'action_by': request.user.id}
                notification_obj = NotificationModel.objects.filter(lead_user_id=lead_object.id)
                if notification_obj.exists():
                    notification_obj.update(is_completed=True)
                if "remarks" in request.data:
                    lead_status_data['remarks'] = request.data["remarks"]
                status_serializer_data = LeadStatusModelSerializers(data=lead_status_data)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()
                return Response({'details': 'Lead data rejected'}, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "Please check the id of the lead entered"},
                                status=status.HTTP_400_BAD_REQUEST)


class ContactAddViewSet(ModelViewSet):
    """
    Class for CRUD operations in the ContactModel
    """

    permission_classes = [IsAdminOrCreateOnly]
    queryset = models.ContactModel.objects.all()
    serializer_class = ContactModelSerializers
    http_method_names = ['get', 'post']

    def create(self, request, *args, **kwargs):
        contact_serializer_data = self.serializer_class(data=request.data)

        # Entering the contact data to ContactModel Table
        contact_serializer_data.is_valid()
        contact_serializer_data.save()

        output_data = contact_serializer_data.data

        # Sending email to the admin email(on adding a new data in ContactModel)
        contact_info_send_email(request, output_data)
        return Response(output_data, status=status.HTTP_201_CREATED)


class ListCountries(APIView):
    """
    Class for listing countries
    """
    permission_classes = [AllowAny]

    def get(self, request):
        data_list = list()
        for country_code, country_name in list(countries):
            data_list.append({"display_name": country_name, "value": country_code})
        return Response({'country_list': data_list}, status=status.HTTP_200_OK)


class ListCurrencies(APIView):
    """
    Class for listing currencies
    """
    permission_classes = [AllowAny]

    def get(self, request):
        data_list = list()
        for currency in list(currencies):
            if currency.alpha_3 != 'XXX':
                data_list.append({"currency_name": currency.name, "currency_code": currency.alpha_3})
        return Response({'currency_list': data_list}, status=status.HTTP_200_OK)
