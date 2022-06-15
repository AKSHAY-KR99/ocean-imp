import imp
import random
import logging
import threading
import django_filters.rest_framework
from datetime import timedelta
from itertools import chain
from django.http import HttpResponse, HttpResponseRedirect
from inflection import re
import requests
from django.contrib.auth import authenticate
from django.db.models import Q, Sum
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import update_last_login
from rest_framework import status, filters, pagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
# from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from .permissions import IsCustomAdminUser
from contact_app.models import LeadsModel, LeadStatusModel, ON_BOARDING_CUSTOMER, ON_BOARDING_REJECTED
from . import models
from .serializers import UserModelSerializers, UserLoginSerializer, UserDetailSerializers, SupplierSmeDetailSerializers, \
    OnBoardEmailDataSerializers, UserContactDetailsSerializers, SMEOnboardReviewMailDataSerializer
from transaction_app.serializers import NotificationModelSerializer
from contact_app.serializers import LeadsModelSerializers, LeadStatusModelSerializers
from .validators import validate_password
from transaction_app.models import MasterContractStatusModel, AccountDetailsModel, NotificationModel
from utils.utility import user_activated_send_email, user_deactivated_send_email, generate_next_step_value, \
    get_user_available_amount, check_sme_missing_field_onboarding, check_update_credit, send_sme_review_email, \
    generate_sme_zip_file, generate_request_status, xero_bank_statement, xero_profit_loss, \
    xero_balance_sheet, xero_tenant_id_generation, xero_token_generation, refreshing_access_token, \
    send_otp_for_login_or_set_password, xero_organization_details, get_organization_details, \
    json_to_excel_response, profit_loss_response, get_codat_xero_profit_and_loss_data, \
    get_codat_xero_balance_sheet_data, \
    codat_response, password_reset_send_email, codat_get_company_by_id, disconnect_codat
from os.path import exists
import pdb;


class UserModelViewSet(ModelViewSet):
    """
    Class for Create, List, Retrieve operation of users (User Model)
    """
    queryset = models.User.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = UserModelSerializers
    pagination_class = PageNumberPagination
    http_method_names = ['get', 'post', 'put']

    def update(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            input_dict = dict()
            queryset_filter = self.get_queryset().filter(is_deleted=False)
            instance_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            if 'user_active_status' in request.data:
                input_dict['is_active'] = request.data['user_active_status']
            if 'credit_limit' in request.data:
                if instance_object.user_role == settings.SME["number_value"]:
                    check_status = check_update_credit(instance_object, request.data['credit_limit'])
                    if not check_status[0]:
                        return Response({'detail': check_status[1]}, status=status.HTTP_400_BAD_REQUEST)
                    input_dict['credit_limit'] = request.data['credit_limit']
                else:
                    return Response({'detail': 'Cannot add credit limit for non SME users'},
                                    status=status.HTTP_400_BAD_REQUEST)
            # if kwargs['pk'] == str(request.user.id):
            editable_fields = ['first_name', 'last_name', 'phone_number']
            for field in editable_fields:
                if field in request.data and request.data[field] is not None:
                    input_dict[field] = request.data[field]
            if 'profile_image' in request.FILES:
                input_dict["profile_image"] = request.FILES.get("profile_image")
            user_data_serializer = self.serializer_class(instance_object, data=input_dict, partial=True,
                                                         context={"request": request})
            user_data_serializer.is_valid(raise_exception=True)
            self.perform_update(user_data_serializer)
            if request.data.get('country_name'):
                request.data['company_registered_in'] = request.data.get('country_name')
            user_details = models.UserDetailModel.objects.filter(company_details=instance_object.id)
            if user_details.exists():
                user_details_serializer = UserDetailSerializers(user_details.last(), request.data, partial=True)
                user_details_serializer.is_valid(raise_exception=True)
                user_details_serializer.save()
            leads_obj = LeadsModel.objects.filter(sign_up_email=instance_object.email)
            if leads_obj.exists():
                leads_serializer = LeadsModelSerializers(leads_obj.last(), data=request.data, partial=True)
                leads_serializer.is_valid(raise_exception=True)
                leads_serializer.save()
            return Response({'message': 'Successfully updated the user data',
                             'data': user_data_serializer.data}, status=status.HTTP_200_OK)

        else:
            if kwargs['pk'] == str(request.user.id):
                queryset_filter = self.get_queryset().filter(is_deleted=False)
                instance_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
                input_dict = dict()
                editable_fields = ['first_name', 'last_name', 'phone_number']
                for field in editable_fields:
                    if field in request.data and request.data[field] is not None:
                        input_dict[field] = request.data[field]
                input_dict["profile_image"] = request.FILES.get("profile_image")
                user_data_serializer = self.serializer_class(instance_object, data=input_dict, partial=True,
                                                             context={"request": request})
                user_data_serializer.is_valid(raise_exception=True)
                self.perform_update(user_data_serializer)

                # Updating the LeadsModel Table
                lead_object = LeadsModel.objects.filter(sign_up_email=instance_object.email)
                if lead_object.exists():
                    for field in editable_fields:
                        if field in input_dict and input_dict[field] is not None:
                            lead_object[0].field = input_dict[field]
                    lead_object[0].save()

                return Response({'message': 'Successfully updated the user data',
                                 'data': user_data_serializer.data}, status=status.HTTP_200_OK)

            else:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)

    def retrieve(self, request, *args, **kwargs):
        if kwargs['pk'] == str(request.user.id) or request.user.user_role == settings.ADMIN["number_value"]:
            queryset_filter = self.get_queryset().filter(is_deleted=False)
            user_object = get_object_or_404(queryset_filter, pk=kwargs['pk'])
            serializer_data = self.serializer_class(user_object, context={"request": request})
            output_data = serializer_data.data
            output_data['company_email'] = output_data['email']

            if hasattr(user_object.on_boarding_details, 'company_website'):
                output_data['company_website'] = user_object.on_boarding_details.company_website

            # Fetching the LeadsModel Table data
            sme_leads_object = LeadsModel.objects.filter(sign_up_email=output_data['email'])
            if sme_leads_object.exists():
                output_data['company_registered_in'] = sme_leads_object[0].company_registered_in.code
                output_data['annual_revenue'] = sme_leads_object[0].annual_revenue
                output_data['description'] = sme_leads_object[0].description

            return Response({'data': output_data}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def list(self, request, *args, **kwargs):
        self.pagination_class.page_size = 1000
        if request.user.user_role == settings.ADMIN["number_value"]:
            from_date = request.GET.get("from_date")
            to_date = request.GET.get("to_date")
            user_role = self.request.query_params.get('user_role')
            is_active = self.request.query_params.get('is_active')
            queryset_data = self.get_queryset()

            if to_date and from_date:
                queryset_data = queryset_data.filter(on_boarding_details__date_created__gte=from_date,
                                                     on_boarding_details__date_created__lte=to_date)
            if request.GET.get("next_action") == "kyc_pending":
                queryset_data = queryset_data.filter(on_board_status=models.ON_BOARD_IN_PROGRESS)

            if 'credit_limit_from' in request.GET and 'credit_limit_to' in request.GET:
                if float(request.GET['credit_limit_from']) == 0:
                    queryset_data = self.queryset.filter(credit_limit__lt=float(request.GET['credit_limit_to']))
                elif float(request.GET['credit_limit_to']) == 0:
                    queryset_data = self.queryset.filter(credit_limit__gte=float(request.GET['credit_limit_from']))
                else:
                    queryset_data = self.queryset.filter(credit_limit__gte=float(request.GET['credit_limit_from']),
                                                         credit_limit__lte=float(request.GET['credit_limit_to']))

            if 'approved_by' in request.GET:
                queryset_data = queryset_data.filter(approved_by__contains=request.GET['approved_by'])

            if request.GET.get("user_action") == "awaiting_onboard":
                queryset_data = queryset_data.filter(on_board_status=models.ON_BOARD_USER_CREATED)
            elif request.GET.get("user_action") == "credit_check":
                queryset_data = queryset_data.filter(on_board_status=models.ON_BOARD_IN_PROGRESS)
            elif request.GET.get("user_action") == "activate":
                queryset_data = queryset_data.filter(on_board_status=models.ON_BOARD_USER_REVIEWED)
            elif request.GET.get("user_action") == "master_contract":
                queryset_data = queryset_data.filter(on_board_status=models.ON_BOARD_COMPLETED,
                                                     master_contract__isnull=True)

            if request.GET.get("user_action") == "deleted":
                queryset_data = queryset_data.filter(is_deleted=True, user_role=user_role)
                page = self.paginate_queryset(queryset_data)
                if page is not None:
                    total_requested_amount = LeadsModel.objects.all().aggregate(Sum("invoice_amount"))
                    serializer = self.serializer_class(page, many=True, context={"request": request})
                    paginated_response = self.get_paginated_response(serializer.data)
                    paginated_response.data['total_requested_amount'] = total_requested_amount['invoice_amount__sum']
                    return paginated_response

            context_dict = dict()
            context_dict['request'] = request
            if 'over_due_from' in request.GET and 'over_due_to' in request.GET:
                context_dict['over_due_from'] = float(request.GET['over_due_from'])
                context_dict['over_due_to'] = float(request.GET['over_due_to'])

            if is_active == "1":
                if user_role:
                    queryset_data = queryset_data.filter(user_role=user_role, is_user_onboard=True,
                                                         is_active=True, is_deleted=False)
                else:
                    return Response({'detail': 'Please provide a user_role parameter'},
                                    status=status.HTTP_400_BAD_REQUEST)
            elif is_active == "0":
                if user_role:
                    queryset_data = queryset_data.filter(user_role=user_role, is_deleted=False)
                else:
                    return Response({'detail': 'Please provide a user_role parameter'},
                                    status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'detail': 'Please provide is_active parameter'},
                                status=status.HTTP_400_BAD_REQUEST)
            page = self.paginate_queryset(queryset_data)
            if page is not None:
                total_requested_amount = LeadsModel.objects.all().aggregate(Sum("invoice_amount"))
                serializer = self.serializer_class(page, many=True, context=context_dict)
                paginated_response = self.get_paginated_response(serializer.data)
                result_list = list()
                for items in paginated_response.data['results']:
                    if items is not None:
                        result_list.append(items)
                paginated_response.data['results'] = result_list
                paginated_response.data['total_requested_amount'] = total_requested_amount['invoice_amount__sum']
                return paginated_response
        elif request.user.user_role == settings.SME["number_value"] and request.user.is_user_onboard:
            user_set = models.User.objects.filter(user_role=settings.SUPPLIER[
                "number_value"], is_user_onboard=True, is_active=True, is_deleted=False)
            get_lead_data = LeadsModel.objects.filter(created_by=request.user)
            main_list = list()
            for lead in get_lead_data:
                sme_created_user = get_object_or_404(models.User, email=lead.sign_up_email)
                if not sme_created_user.is_user_onboard:
                    main_list.append(sme_created_user)
            final_users_list = list(chain(user_set, main_list))
            page = self.paginate_queryset(final_users_list)
            if page is not None:
                serializer = SupplierSmeDetailSerializers(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.SUPPLIER["number_value"] and request.user.is_user_onboard:
            page = self.paginate_queryset((self.get_queryset().filter(user_role=settings.SME[
                "number_value"], is_user_onboard=True, is_deleted=False, is_active=True)))
            if page is not None:
                serializer = SupplierSmeDetailSerializers(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)

        elif request.user.user_role == settings.FACTOR["number_value"]:
            user_role = self.request.query_params.get('user_role')
            if user_role:
                if int(user_role) in [settings.SME["number_value"], settings.SUPPLIER["number_value"]]:
                    page = self.paginate_queryset((self.get_queryset().filter(user_role=user_role, is_user_onboard=True,
                                                                              is_active=True, is_deleted=False)))
                else:
                    return Response({'detail': 'Please provide the correct user_role parameter'},
                                    status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'detail': 'Please provide user_role parameter'},
                                status=status.HTTP_400_BAD_REQUEST)
            if page is not None:
                serializer = SupplierSmeDetailSerializers(page, many=True)
                return self.get_paginated_response(serializer.data)

        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class UserDetailBySlug(RetrieveAPIView):
    """
    Class for getting user details using user unique slug value
    """
    queryset = models.User.objects.all()
    permission_classes = [AllowAny]
    lookup_field = "slug_value"

    def retrieve(self, request, *args, **kwargs):
        queryset_filter = self.get_queryset().filter(is_deleted=False)
        user_object = get_object_or_404(queryset_filter, slug_value=kwargs['slug_value'])
        next_step = generate_next_step_value(settings.APP_FROM_EMAIL_SLUG_VALUE, user_object)
        return Response({'message': 'Returning user email', 'email': user_object.email, "next_step": next_step},
                        status=status.HTTP_200_OK)


class UserLoginView(APIView):
    """
    Class for user login(active users)
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_object = models.User.objects.get(email=request.data['email'])
        if user_object.on_board_status == models.ON_BOARD_REJECTED:
            return Response({'Details': 'Your account has been rejected'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'message': 'User authentication first phase completed, OTP sent to the user phone number',
                'session_id': serializer.data['session_id'],
                'next_step': settings.APP_OTP_VALIDATION_PAGE
            }, status=status.HTTP_200_OK)


class UserPasswordSetView(APIView):
    """
    Class for setting the password for a new user
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if 'email' not in request.data or 'password' not in request.data:
            return Response({
                "email/password": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password=request.data['password'])
        except ValidationError as error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        user_object = get_object_or_404(models.User, email=request.data['email'], is_deleted=False)
        if not user_object.is_active:
            # Setting the password and updating on_board_status
            if user_object.is_staff or user_object.user_role == settings.FACTOR_ROLE_VALUE:
                user_object.on_board_status = models.ON_BOARD_COMPLETED
                user_object.is_user_onboard = True
            else:
                user_object.on_board_status = models.ON_BOARD_PASSWORD_SET

            user_object.is_active = True
            user_object.set_password(request.data['password'])
            user_object.save()

            # function for generating otp
            otp_value = int(random.randint(100000, 999999))
            login_tracker_object = models.LoginTrackerModel.objects.create(user=user_object, otp_value=otp_value,
                                                                           otp_status=models.OTP_SENT_STRING)
            login_tracker_object.save()
            session_id = login_tracker_object.session_id

            # function for sending otp
            send_otp_for_login_or_set_password(user_object, otp_value)
            return Response({
                'message': 'User password set, OTP sent to the user phone number',
                'session_id': session_id,
                'next_step': settings.APP_OTP_VALIDATION_PAGE
            }, status=status.HTTP_200_OK)
        else:
            user_object.set_password(request.data['password'])
            user_object.save()

            # function for generating otp
            otp_value = int(random.randint(100000, 999999))
            login_tracker_object = models.LoginTrackerModel.objects.create(user=user_object, otp_value=otp_value,
                                                                           otp_status=models.OTP_SENT_STRING)
            login_tracker_object.save()
            session_id = login_tracker_object.session_id

            # function for sending otp
            send_otp_for_login_or_set_password(user_object, otp_value)
            return Response({
                'message': 'User password set, OTP sent to the user phone number',
                'session_id': session_id,
                'next_step': settings.APP_OTP_VALIDATION_PAGE
            }, status=status.HTTP_200_OK)


class OtpValidationView(APIView):
    """
    Class for validating the OTP entered
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if "session_id" not in request.data or "otp_value" not in request.data:
            return Response({
                "session_id/otp_value": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)

        time_threshold = timezone.now() - timedelta(minutes=settings.OTP_EXPIRY_TIME)
        if int(request.data['otp_value']) == 777777 and settings.PRODUCTION is False:
            login_tracker_object = models.LoginTrackerModel.objects.filter(session_id=request.data["session_id"],
                                                                           otp_created_date__gte=time_threshold)
        else:
            login_tracker_object = models.LoginTrackerModel.objects.filter(session_id=request.data["session_id"],
                                                                           otp_value=request.data["otp_value"],
                                                                           otp_created_date__gte=time_threshold)
        if login_tracker_object.exists():
            login_tracker_object.update(otp_status=models.OTP_VERIFIED_STRING)
            return Response({'message': 'OTP validation completed',
                             "next_step": settings.APP_AUTH_TOKEN_GENERATOR}, status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'OTP value entered not correct or it has expired'},
                            status=status.HTTP_401_UNAUTHORIZED)


class ReviewUserMailView(APIView):
    """
    Class for sending mail to factoring users for reviewing a sme user
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        if "email_list" not in request.data:
            return Response({
                "email_list": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        if not request.data["email_list"]:
            return Response({'detail': 'Please enter at least one email id'}, status=status.HTTP_400_BAD_REQUEST)
        if "user_onboard_id" not in request.data:
            return Response({
                "user_onboard_id": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        if "template_data" not in request.data:
            return Response({
                "template_data": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        if "remarks" not in request.data or request.data["remarks"] is None:
            remarks = ""
        else:
            remarks = request.data["remarks"]
        bcc_email = request.data.get('email_list_bcc', [])
        cc_email = request.data.get('email_list_cc', [])
        user_onboard_object = get_object_or_404(models.UserDetailModel, pk=request.data["user_onboard_id"])
        user_object = user_onboard_object.company_details.all()[0]
        lead_object = LeadsModel.objects.get(company_email=user_object.email)
        if user_object.on_board_status not in [models.ON_BOARD_IN_PROGRESS, models.ON_BOARD_USER_REVIEWED,
                                               models.ON_BOARD_COMPLETED] or \
                user_object.user_role != settings.SME["number_value"]:
            return Response({'detail': 'Please check the onboard user id added'}, status=status.HTTP_400_BAD_REQUEST)
        if 'subject' in request.data:
            email_subject = request.data['subject']
        else:
            email_subject = settings.EMAIL_USER_DATA_REVIEW
        send_sme_review_email(email_subject, request.data["email_list"], user_object,
                              request.data['template_data'], remarks, lead_object.company_name, bcc_email, cc_email)

        if user_object.on_board_status == models.ON_BOARD_IN_PROGRESS:
            user_object.on_board_status = models.ON_BOARD_USER_REVIEWED
            user_object.save()
        email_dict = dict()
        email_list = list()
        for email in request.data["email_list"]:
            email_dict['email'] = email
            email_list.append(email_dict)
        review_mail_serilaizer = SMEOnboardReviewMailDataSerializer(data=email_list,
                                                                    many=True,
                                                                    context={"user_detail": user_onboard_object})
        review_mail_serilaizer.is_valid(raise_exception=True)
        review_mail_serilaizer.save()

        email_object = list(models.OnBoardEmailData.objects.filter(email__in=request.data["email_list"]
                                                                   ).values_list('email', flat=True))
        email_list = []
        for email in list(set(request.data["email_list"]) - set(email_object)):
            email_list.append(models.OnBoardEmailData(email=email))
        models.OnBoardEmailData.objects.bulk_create(email_list)
        return Response({'message': 'Shared the user onboard data to the given email ids'}, status=status.HTTP_200_OK)


class UserAuthTokenGenerationView(APIView):
    """
    Class for creating Auth token against a user
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if "session_id" not in request.data or "password" not in request.data:
            return Response({
                "session_id/password": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)

        time_threshold = timezone.now() - timedelta(minutes=5)
        login_tracker_object = models.LoginTrackerModel.objects.filter(session_id=request.data["session_id"],
                                                                       otp_created_date__gte=time_threshold,
                                                                       otp_status=models.OTP_VERIFIED_STRING)
        if login_tracker_object.exists():
            user_object = models.User.objects.get(id=login_tracker_object[0].user.id)
            user = authenticate(email=user_object.email, password=request.data["password"])
            if user is not None:
                refresh = RefreshToken.for_user(user)
                update_last_login(None, user)
                next_step = generate_next_step_value(settings.APP_AUTH_TOKEN_GENERATOR, user_object)
                return Response({'message': 'User authentication completed', 'access_token': str(refresh.access_token),
                                 'refresh_token': str(refresh),
                                 'next_step': next_step}, status=status.HTTP_200_OK)
            else:
                return Response({'detail': 'User credentials entered not correct'},
                                status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'detail': 'session id entered not correct or it has expired or otp not verified'},
                            status=status.HTTP_401_UNAUTHORIZED)


class ActivatingUserView(APIView):
    """
    Class for activating users
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        if 'email' not in request.data or 'activate_action_status' not in request.data:
            return Response({
                "email/activate_action_status": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)

        user_object = get_object_or_404(models.User, email=request.data['email'], is_deleted=False)
        # Check if user is already activated
        if user_object.is_user_onboard:
            return Response({'detail': 'User account is already activated'}, status=status.HTTP_400_BAD_REQUEST)
        # Check if sme user have the needed on board status and input contains credit_limit value
        if user_object.user_role == settings.SME["number_value"]:
            if user_object.on_board_status == models.ON_BOARD_USER_REVIEWED:
                if request.data['activate_action_status'] is True:
                    if 'credit_limit' not in request.data:
                        return Response({
                            "credit_limit": [
                                "This field is required."
                            ]
                        }, status=status.HTTP_400_BAD_REQUEST)
                    if not request.data['credit_limit']:
                        return Response({
                            "detail": "Credit limit cannot be empty"},
                            status=status.HTTP_400_BAD_REQUEST)
                    user_object.credit_limit = request.data['credit_limit']
                    notification_data = {"user": user_object.id, "notification": "User was Activated",
                                         "type": settings.USER_ACTIVATED,
                                         "description": "Master Contract Creation is Pending"}
                    notification_serializer = NotificationModelSerializer(data=notification_data)

                    if notification_serializer.is_valid(raise_exception=True):
                        notification_serializer.save()

            # elif user_object.on_board_status == models.ON_BOARD_REJECTED:
            #   return Response({'detail': 'Sorry, You account has been rejected.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'detail': 'Review of user on board data pending'}, status=status.HTTP_400_BAD_REQUEST)
        # Check if supplier user have the needed on board status and if input contains credit_limit value deleting it
        elif user_object.user_role == settings.SUPPLIER["number_value"]:
            if user_object.on_board_status == models.ON_BOARD_IN_PROGRESS:
                if 'credit_limit' in request.data:
                    del request.data['credit_limit']
            else:
                return Response({'detail': 'User has not entered the details page, after completing only then admin '
                                           'can activate the user'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'detail': 'Please check the user email entered'}, status=status.HTTP_400_BAD_REQUEST)

        notification_obj = NotificationModel.objects.filter(user_id=user_object.id,
                                                            type=settings.USER_DETAILS_ADDED)
        if notification_obj.exists():
            notification_obj.update(is_completed=True)
        if request.data['activate_action_status']:
            user_object.on_board_status = models.ON_BOARD_COMPLETED
            user_object.is_user_onboard = True
            if 'approved_by' in request.data:
                user_object.approved_by = request.data['approved_by']
            user_object.save()
            user_activated_send_email(subject=settings.ACCOUNT_ACTIVATED, model_instance=user_object,
                                      recipient_email=user_object.email)
            lead_object = get_object_or_404(LeadsModel.objects.filter(Q(company_email=user_object.email) |
                                                                      Q(alternate_email=user_object.email)))
            # lead_object.current_status = ON_BOARDING_CUSTOMER
            lead_object.save()
            return Response({'message': 'User has been activated, mail send to the user'}, status=status.HTTP_200_OK)
        else:
            user_object.on_board_status = models.ON_BOARD_REJECTED
            user_object.is_user_onboard = False
            user_object.is_active = False
            user_object.save()
            notification_obj = NotificationModel.objects.filter(user_id=user_object.id,
                                                                type=settings.USER_DETAILS_ADDED)
            if notification_obj.exists():
                notification_obj.update(is_completed=True)
            user_deactivated_send_email(subject=settings.ACCOUNT_DEACTIVATED, model_instance=user_object,
                                        recipient_email=user_object.email)
            lead_object = get_object_or_404(LeadsModel.objects.filter(Q(company_email=user_object.email) |
                                                                      Q(alternate_email=user_object.email)))
            lead_object.current_status = ON_BOARDING_CUSTOMER
            lead_object.save()
            return Response({'message': 'User account not activated, mail send to the user'}, status=status.HTTP_200_OK)


class UserDetailModelViewSet(ModelViewSet):
    """
    Class for create, list and retrieve operation of the UserDetailModel(SME/Supplier)
    """
    serializer_class = UserDetailSerializers
    queryset = models.UserDetailModel.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    pagination_class = PageNumberPagination
    filterset_fields = ['company_name']
    http_method_names = ['get', 'post', 'put']

    def create(self, request, *args, **kwargs):
        if request.user.on_board_status == models.ON_BOARD_PASSWORD_SET:
            if request.user.on_boarding_details is not None:
                return Response({'detail': 'User has already entered the detail page using xero'},
                                status=status.HTTP_400_BAD_REQUEST)
            file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(request.user.id)}/' \
                        f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
            serializer_data = request.data.copy()
            serializer_data["user_detail_path"] = file_path
            if request.user.user_role == settings.SME["number_value"]:
                key_status = check_sme_missing_field_onboarding(list(serializer_data.keys()),
                                                                False)
                if not key_status:
                    return Response({'detail': 'Missing needed input data for creating user on board details'},
                                    status=status.HTTP_400_BAD_REQUEST)

            user_detail_serializer = self.serializer_class(data=serializer_data, context={"request": request})
            user_detail_serializer.is_valid(raise_exception=True)
            user_detail_object = user_detail_serializer.save()

            request.user.on_board_status = models.ON_BOARD_IN_PROGRESS
            request.user.on_boarding_details = user_detail_object
            request.user.save()

            if request.data.get('additional_contact'):
                additional_contact_serializer = UserContactDetailsSerializers(
                    data=eval(str(request.data['additional_contact'])), many=True,
                    context={'user_details': user_detail_object})
                additional_contact_serializer.is_valid(raise_exception=True)
                additional_contact_serializer.save()

            details_list = list()
            for detail_file_key in settings.USER_DETAIL_ID_KEY:
                for file_object in request.FILES.getlist(detail_file_key):
                    details_list.append(models.UserDetailFilesModel(detail=user_detail_object,
                                                                    detail_id_file=file_object,
                                                                    detail_file_key=detail_file_key))
            models.UserDetailFilesModel.objects.bulk_create(details_list)
            # For creating a zip file of onboard files
            if request.user.user_role == settings.SME["number_value"]:
                threading_process = threading.Thread(target=generate_sme_zip_file,
                                                     args=(user_detail_object.company_details.all()[0].email,))
                threading_process.start()
            leads_obj = LeadsModel.objects.get(sign_up_email=request.user.email)
            if leads_obj.sync_status in [settings.SYNC_COMPLETED, settings.NO_SYNC]:
                notification_data = {"on_boarding_details": user_detail_serializer.data["id"],
                                     "user": request.user.id,
                                     "notification": "User Detail was Added",
                                     "type": settings.USER_DETAILS_ADDED,
                                     "description": "User Activation is Pending"}
                notification_serializer = NotificationModelSerializer(data=notification_data)

                if notification_serializer.is_valid(raise_exception=True):
                    notification_serializer.save()
            return Response({'message': 'User detail has been created',
                             'data': user_detail_serializer.data}, status=status.HTTP_201_CREATED)

        else:
            return Response({'detail': 'User has already entered the details page'},
                            status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        if request.user.on_board_status == models.ON_BOARD_PASSWORD_SET:
            instance_object = self.get_object()
            # keys = ['current_balance_sheet', 'last_year_account_statement', 'last_year_profit_loss']
            # for key in keys:
            #     if key in request.data:
            #         return Response({'details': key + ' is already uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

            serializer_data = request.data.copy()
            if request.user.user_role == settings.SME["number_value"]:
                key_status = check_sme_missing_field_onboarding(list(serializer_data.keys()),
                                                                True)
                if not key_status:
                    return Response({'detail': 'Missing needed input data for creating user on board details'},
                                    status=status.HTTP_400_BAD_REQUEST)
                user_detail_serializer = self.serializer_class(instance_object, data=serializer_data,
                                                               context={"request": request})
                user_detail_serializer.is_valid(raise_exception=True)
                user_detail_object = user_detail_serializer.save()

                request.user.on_board_status = models.ON_BOARD_IN_PROGRESS
                # request.user.on_boarding_details = user_detail_object
                request.user.save()
                contact_ids = []
                if request.data.get('additional_contact'):
                    for contact_obj in eval(str(request.data['additional_contact'])):
                        if contact_obj.get('id'):
                            contact_object = models.UserContactDetails.objects.get(id=contact_obj['id'])
                            additional_contact_serializer = UserContactDetailsSerializers(contact_object,
                                                                                          contact_obj)
                            additional_contact_serializer.is_valid(raise_exception=True)
                            additional_contact_serializer.save()
                        else:
                            additional_contact_serializer = UserContactDetailsSerializers(
                                data=contact_obj, context={'user_details': user_detail_object})
                            additional_contact_serializer.is_valid(raise_exception=True)
                            additional_contact_serializer.save()
                        contact_ids.append(additional_contact_serializer.data['id'])
                models.UserContactDetails.objects.filter(user_details=user_detail_object).exclude(
                    id__in=contact_ids).delete()
                details_list = list()
                for detail_file_key in settings.USER_DETAIL_ID_KEY:
                    for file_object in request.FILES.getlist(detail_file_key):
                        details_list.append(models.UserDetailFilesModel(detail=user_detail_object,
                                                                        detail_id_file=file_object,
                                                                        detail_file_key=detail_file_key))
                models.UserDetailFilesModel.objects.bulk_create(details_list)
                # For creating a zip file of onboard files
                if request.user.user_role == settings.SME["number_value"]:
                    threading_process = threading.Thread(target=generate_sme_zip_file,
                                                         args=(user_detail_object.company_details.all()[0].email,))
                    threading_process.start()
                    leads_obj = LeadsModel.objects.get(sign_up_email=request.user.email)
                    leads_serializer = LeadsModelSerializers(leads_obj, data=request.data, partial=True)
                    leads_serializer.is_valid(raise_exception=True)
                    leads_serializer.save()
                    if leads_obj.sync_status in [settings.SYNC_COMPLETED, settings.NO_SYNC]:
                        notification_obj = NotificationModel.objects.filter(
                            on_boarding_details=user_detail_serializer.data["id"],
                            user=request.user.id, type=settings.USER_DETAILS_ADDED)

                        if not notification_obj.exists():
                            notification_data = {"on_boarding_details": user_detail_serializer.data["id"],
                                                 "user": request.user.id,
                                                 "notification": "User Detail was Added",
                                                 "type": settings.USER_DETAILS_ADDED,
                                                 "description": "User Activation is Pending"}
                            notification_serializer = NotificationModelSerializer(data=notification_data)

                            if notification_serializer.is_valid(raise_exception=True):
                                notification_serializer.save()
                return Response({'message': 'User detail has been created',
                                 'data': user_detail_serializer.data}, status=status.HTTP_201_CREATED)
        else:
            return Response({'detail': 'User has already entered the details page'},
                            status=status.HTTP_400_BAD_REQUEST)
            # On enabling add code for removing old zip file and creating a new zip file with new data
        # (if file can be replaced)
        if request.user.on_board_status == models.ON_BOARD_REJECTED:
            instance_object = self.get_object()
            if instance_object.company_details.get().id == request.user.id:
                user_detail_serializer = self.serializer_class(instance_object, data=request.data, partial=True)
                user_detail_serializer.is_valid(raise_exception=True)
                self.perform_update(user_detail_serializer)
                request.user.on_board_status = models.ON_BOARD_IN_PROGRESS
                request.user.save()
                return Response({'message': 'Successfully updated the user detail data',
                                 'data': user_detail_serializer.data}, status=status.HTTP_200_OK)
        return Response({'detail': "User don't have the permission to update"}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            serializer_data = self.serializer_class(self.get_object())
            output_dict = serializer_data.data
            user_object = self.get_object().company_details.all()[0]
            output_dict['user_email'] = user_object.email
            output_dict['on_board_status'] = user_object.get_on_board_status_display()
            if user_object.credit_limit:
                output_dict['credit_limit'] = user_object.credit_limit
            leads_data = LeadsModelSerializers(instance=LeadsModel.objects.filter(
                company_email=user_object.email).last()).data
            output_dict["country_name"] = leads_data["company_registered_in"]
            if user_object.user_role == settings.SME["number_value"]:
                output_dict['zip_file_url'] = f"{settings.MEDIA_URL}{settings.ON_BOARDING_DATA_BASE_PATH}/" \
                                              f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/" \
                                              f"{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}.zip"

                output_dict["sync_status"] = leads_data["sync_status"]
            return Response({"data": output_dict}, status=status.HTTP_200_OK)
        elif kwargs['pk'] == str(request.user.on_boarding_details.id):
            serializer_data = self.serializer_class(self.get_object())
            output_dict = serializer_data.data
            user_object = self.get_object().company_details.all()[0]
            leads_data = LeadsModelSerializers(instance=LeadsModel.objects.filter(
                company_email=request.user.email).last()).data
            output_dict["country_name"] = leads_data["company_registered_in"]
            output_dict['on_board_status'] = user_object.get_on_board_status_display()
            if user_object.credit_limit:
                output_dict['credit_limit'] = user_object.credit_limit
            if user_object.user_role == settings.SME["number_value"]:
                output_dict['zip_file_url'] = f"{settings.MEDIA_URL}{settings.ON_BOARDING_DATA_BASE_PATH}/" \
                                              f"{str(user_object.id)}/{settings.ON_BOARDING_DATA_ZIP_FILE_PATH}/" \
                                              f"{settings.ON_BOARDING_DATA_ZIP_FILE_NAME}.zip"
            return Response({"data": output_dict}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

    def list(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            page = self.paginate_queryset((self.get_queryset()))
            if page is not None:
                serializer = self.serializer_class(page, many=True, context={"request": request})
                return self.get_paginated_response(serializer.data)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


# class LogoutView(APIView):
#     permission_classes = (IsAuthenticated,)

#     def get(self, request):
#         # refresh = RefreshToken.for_user(request.user)
#         # print(str(refresh.access_token))
#         tokens = OutstandingToken.objects.filter(user_id=request.user.id)
#         for token in tokens:
#             t, _ = BlacklistedToken.objects.get_or_create(token=token)
#         response = {'message': 'Logged out'}
#         status_code = status.HTTP_205_RESET_CONTENT
#         return Response(response, status=status_code)


class LoggedInUserDetail(APIView):
    """
    Class for retrieving the details of a logged in user
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):

        serializer_data = UserModelSerializers(get_object_or_404(models.User, pk=request.user.id, is_deleted=False),
                                               context={"request": request})
        output_dict = serializer_data.data
        if request.user.user_role != settings.ADMIN["number_value"]:
            leads_object = LeadsModel.objects.get(sign_up_email=request.user.email)
        if request.user.user_role == settings.SME["number_value"]:
            output_dict['user_available_amount'] = get_user_available_amount(output_dict['id'])
            if leads_object.company_id:
                output_dict['connection_status'] = bool(
                    codat_get_company_by_id(leads_object.company_id).get('dataConnections'))
        output_dict['is_master_contract_approved'] = False
        if request.user.master_contract is not None:
            if MasterContractStatusModel.objects.filter(contract=request.user.master_contract).first().action_taken \
                    == settings.CREDIT_CONTRACT_SME_APPROVED:
                output_dict['is_master_contract_approved'] = True
            else:
                output_dict['is_master_contract_approved'] = False
        if AccountDetailsModel.objects.count():
            is_account_details_added = True
        else:
            is_account_details_added = False
        output_dict['is_account_details_added'] = is_account_details_added

        # For generating data from leads for onboarding
        if request.user.on_board_status == models.ON_BOARD_PASSWORD_SET:
            if request.user.user_role == settings.SME_ROLE_VALUE or request.user.user_role == \
                    settings.SUPPLIER_ROLE_VALUE:
                output_dict['company_name'] = leads_object.company_name
                output_dict['company_website'] = leads_object.company_website
                output_dict['sync_status'] = leads_object.sync_status
                if leads_object.company_id:
                    response = requests.get(f"https://api.codat.io/companies/{leads_object.company_id}",
                                            headers={"Content-Type": "application/json",
                                                     "Accept": "application/json",
                                                     "Authorization": settings.CODAT_AUTHORIZATION_KEY})
                    response_data = response.json()
                    output_dict['redirect_url'] = response_data.get('redirect')

        return Response({"data": output_dict}, status=status.HTTP_200_OK)


class GenerateOnboardTemplateData(APIView):
    """
    Class for generating on boarding template data
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_role != settings.ADMIN["number_value"]:
            if request.data['user_onboard_id'] != request.user.on_boarding_details.id:
                return Response({"detail": "You do not have permission to perform this action."},
                                status=status.HTTP_403_FORBIDDEN)
        onboard_object = get_object_or_404(models.UserDetailModel, pk=request.data['user_onboard_id'])
        lead_object = LeadsModelSerializers(instance=LeadsModel.objects.get(
            company_email=onboard_object.company_details.all()[0].email)).data
        template_data = UserDetailSerializers(onboard_object).data
        template_data["country_name"] = lead_object["company_registered_in"]
        # 'detail_id_files' is an array as multiple id files can be there

        for onboard_data_key in template_data.keys():
            if onboard_data_key != 'detail_id_files':
                if isinstance(template_data[onboard_data_key], str):
                    template_data[onboard_data_key] = template_data[onboard_data_key].replace(f"{settings.MEDIA_URL}"
                                                                                              f"{onboard_object.user_detail_path}",
                                                                                              "")
        id_data_list = list()
        for id_data in template_data['detail_id_files']:
            id_data_list.append({key: id_data[key].replace(f"{settings.MEDIA_URL}{onboard_object.user_detail_path}", '')
                                 for key in id_data.keys() if isinstance(id_data[key], str)})
        template_data['detail_id_files'] = id_data_list

        onboard_file_base_path = f"{settings.DJANGO_ROOT_DIR}/{settings.ONBOARD_TEMPLATE_FILE_PATH}"
        if onboard_object.company_details.all()[0].user_role == settings.SME["number_value"]:
            onboard_file_path = f"{onboard_file_base_path}/{settings.ONBOARD_TEMPLATE_SME_FILE_NAME}"
        elif onboard_object.company_details.all()[0].user_role == settings.SUPPLIER["number_value"]:
            onboard_file_path = f"{onboard_file_base_path}/{settings.ONBOARD_TEMPLATE_SUPPLIER_FILE_NAME}"
        with open(onboard_file_path, 'r') as f:
            file_data = f.read()
        return Response({"data": file_data, "metaData": template_data}, status=status.HTTP_200_OK)


class DeleteUser(APIView):
    """
    Class for Deleting user
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request, **kwargs):
        user_object = get_object_or_404(models.User, pk=kwargs['user_id'])
        output_dict = dict()
        if not user_object.is_staff:
            user_object.is_deleted = True
            user_object.is_active = False
            user_object.save()
            lead_user = LeadsModel.objects.filter(sign_up_email=user_object.email)
            if lead_user.exists():
                lead_object = lead_user.first()
                lead_object.is_deleted = True
                lead_object.is_active = False
                lead_object.save()
                if lead_object.company_id is not None:
                    if lead_object.company_id != '':
                        codat_connections = codat_get_company_by_id(lead_object.company_id).get('dataConnections')
                        if codat_connections:
                            for connections in codat_connections:
                                if 'id' in connections:
                                    response = disconnect_codat(lead_object.company_id, connections['id'])
                                if response.json():
                                    output_dict['message'] = "Successfully deleted the codat connection"
                                else:
                                    output_dict['message'] = "There is some error in disconnecting the codat"
                        lead_object.company_id = None
                        lead_object.save()
            notification_obj = NotificationModel.objects.filter(user=user_object.id)
            if notification_obj.exists():
                notification_obj.update(is_deleted=True)
        else:
            return Response({"detail": "Cannot delete admin users."},
                            status=status.HTTP_403_FORBIDDEN)
        output_dict['detail'] = "Successfully deleted the user"
        return Response(output_dict,
                        status=status.HTTP_200_OK)


class UserReactivateAPI(APIView):
    """
    Class for Reactivating Deleted user
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request, **kwargs):
        user_info = models.User.objects.filter(pk=kwargs['user_id'], is_deleted=True)
        if user_info.exists():
            user_object = user_info.first()
            if not user_object.is_staff:
                user_object.is_deleted = False
                if user_object.on_board_status != models.ON_BOARD_USER_CREATED:
                    user_object.is_active = True
                user_object.save()
                lead_user = LeadsModel.objects.filter(sign_up_email=user_object.email, is_deleted=True)
                if lead_user.exists():
                    lead_object = lead_user.first()
                    lead_object.is_deleted = False
                    lead_object.save()
                notification_obj = NotificationModel.objects.filter(user=user_object.id, is_deleted=True)
                if notification_obj.exists():
                    notification_obj.update(is_deleted=False)
            else:
                return Response({"detail": "Cannot Re-activate admin users."},
                                status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": "User re-acivated successfully."},
                            status=status.HTTP_200_OK)
        else:
            return Response({"detail": "No user found"},
                            status=status.HTTP_400_BAD_REQUEST)


class XeroAuthUrlAPI(APIView):
    """
    Class for Generating Auth Url
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_role == settings.SME["number_value"]:
            auth_url = settings.AUTH_URL_GENERATOR + '&client_id=' + settings.CLIENT_ID \
                       + '&redirect_uri=' + settings.REDIRECT_URI + '&scope=' + settings.SCOPES + \
                       '&state=' + settings.STATE
            return Response({'message': 'Xero access link',
                             'Auth_url': auth_url}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'You do not have permission to perform this function'},
                            status=status.HTTP_400_BAD_REQUEST)


# # class XeroCallbackAPI(APIView):
#     """
#     Class for getting the required files from user
#     """
#     permission_classes = [IsAuthenticated]

#     def get(self, request, *args, **kwargs):
#         if request.user.user_role == settings.SME['number_value']:
#             user_object = models.User.objects.get(pk=request.user.id)
#             try:
#                 xero_user = models.XeroAuthTokenModel.objects.get(user=request.user.id)
#             except models.XeroAuthTokenModel.DoesNotExist:
#                 xero_user = None
#             file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(request.user.id)}/' \
#                         f'{settings.ON_BOARDING_DATA_FILE_PATH}/'     
#             if xero_user is None:
#                 code = self.request.query_params.get('code')
#                 tokens = xero_token_generation(code=code)
#                 if tokens is False:
#                     return Response(
#                         {'details': 'Please generate auth-url. your dont have any auth code for generating tokens.'},
#                         status=status.HTTP_400_BAD_REQUEST)
#                 else:
#                     token_object = models.XeroAuthTokenModel(user=user_object, access_token=tokens[0],
#                                                              refresh_token=tokens[1])
#                     token_object.save()

#                 tenant_id = xero_tenant_id_generation(token_object.access_token)
#                 balance_sheet_response = xero_balance_sheet(token_object.access_token, tenant_id)
#                 profit_loss = xero_profit_loss(token_object.access_token, tenant_id)
#                 bank_statement = xero_bank_statement(token_object.access_token, tenant_id)
#                 json_to_excel_format(balance_sheet_response, request.user)
#                 json_to_excel_format(profit_loss, request.user)
#                 json_to_excel_format(bank_statement, request.user)
#             else:
#                 if not xero_tenant_id_generation(access_token=xero_user.access_token):
#                     new_tokens = refreshing_access_token(request.user.id)
#                     xero_user.access_token = new_tokens[0]
#                     xero_user.refresh_token = new_tokens[1]
#                     xero_user.save()
#                     tenant_id = xero_tenant_id_generation(access_token=new_tokens[0])
#                 else:
#                     tenant_id = xero_tenant_id_generation(access_token=xero_user.access_token)
#                     balance_sheet_response = xero_balance_sheet(xero_user.access_token, tenant_id)
#                     profit_loss = xero_profit_loss(xero_user.access_token, tenant_id)
#                     bank_statement = xero_bank_statement(xero_user.access_token, tenant_id)

#                 json_to_excel_format(balance_sheet_response, request.user)
#                 json_to_excel_format(profit_loss, request.user)
#                 json_to_excel_format(bank_statement, request.user)

#             #Adding xero files to userdetail object
#             serializer_data = dict()    
#             serializer_data["user_detail_path"] = file_path
#             user_detail_serializer = UserDetailSerializers(data=serializer_data, context={"request": request})
#             user_detail_serializer.is_valid(raise_exception=True)
#             user_detail_object = user_detail_serializer.save()

#             user_detail_object.current_balance_sheet = file_path + "BalanceSheet.xlsx"
#             user_detail_object.last_year_account_statement = file_path + "BankSummary.xlsx"
#             user_detail_object.last_year_profit_loss = file_path + "ProfitAndLoss.xlsx"
#             user_detail_object.save()

#             request.user.on_boarding_details = user_detail_object
#             request.user.save()
#             return Response({'message': 'OK', 'balance sheet': balance_sheet_response, 'profit loss': profit_loss,
#                                 'bank summary': bank_statement, 'user_details': user_detail_serializer.data },
#                             status=status.HTTP_200_OK)
#         else:
#             return Response({'message': 'You do not have permission to perform this function'},
#                             status=status.HTTP_400_BAD_REQUEST)


class XeroTokenAPI(APIView):
    """
       Class for getting the tokens
   """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.user_role == settings.SME['number_value']:
            code = self.request.query_params.get('code')
            token_response = requests.post(url=settings.TOKEN_URL,
                                           headers={'Authorization': 'Basic ' + settings.BASIC_TOKEN},
                                           data={'grant_type': 'authorization_code',
                                                 'code': code,
                                                 'redirect_uri': settings.REDIRECT_URI})
            logger = logging.getLogger(__name__)
            logger.info("user :")
            logger.info(request.user)
            logger.info("Response for token :")
            logger.info(token_response)
            logger.info("JSON response :")
            logger.info(token_response.json())
            json_response = token_response.json()

            access_token = json_response['access_token']
            refresh_token = json_response['refresh_token']

            tenant_id = xero_tenant_id_generation(access_token)
            balance_sheet_response = xero_balance_sheet(access_token, tenant_id)
            profit_loss = xero_profit_loss(access_token, tenant_id)
            bank_statement = xero_bank_statement(access_token, tenant_id)
            organization_details = xero_organization_details(access_token, tenant_id)

            # debt_amount = profit_loss_response(balance_sheet_response, request.user)
            # annual_revenue = profit_loss_response(profit_loss, request.user)
            debt_amount = get_codat_xero_balance_sheet_data('5703c8de-2836-422e-b8a6-153a5a68b9e8', request.user)
            annual_revenue = get_codat_xero_profit_and_loss_data('5703c8de-2836-422e-b8a6-153a5a68b9e8', request.user)
            json_to_excel_response(bank_statement, request.user)

            logger.info("Organization details Response:")
            logger.info(organization_details)
            organization_info = get_organization_details(organization_details)
            logger.info("Organization Info :")
            logger.info(organization_info)

            file_path = f'{settings.ON_BOARDING_DATA_BASE_PATH}/{str(request.user.id)}/' \
                        f'{settings.ON_BOARDING_DATA_FILE_PATH}/'
            # Adding xero files to userdetail object
            serializer_data = dict()
            serializer_data["user_detail_path"] = file_path
            user_detail_serializer = UserDetailSerializers(data=serializer_data, context={"request": request})
            user_detail_serializer.is_valid(raise_exception=True)
            user_detail_object = user_detail_serializer.save()

            user_detail_object.current_balance_sheet = file_path + "BalanceSheet.xlsx"
            user_detail_object.last_year_account_statement = file_path + "BankSummary.xlsx"
            user_detail_object.last_year_profit_loss = file_path + "ProfitAndLoss.xlsx"
            user_detail_object.company_name = organization_info["Organization_name"]
            user_detail_object.company_registration_id = organization_info["RegistrationNumber"]
            user_detail_object.company_physical_address = organization_info["Physical_Address"]
            user_detail_object.company_registered_address = organization_info["Registered_Address"]
            user_detail_object.company_website = organization_info["Website"]
            user_detail_object.company_telephone_number = organization_info["Phone_number"]

            if "Additional Info" in organization_info:
                user_detail_object.additional_info = organization_info["Additional Info"]

            user_detail_object.last_fy_annual_revenue = annual_revenue
            user_detail_object.total_debt_amounts = debt_amount
            user_detail_object.save()

            request.user.on_boarding_details = user_detail_object
            request.user.save()

            leads_object = LeadsModel.objects.filter(company_email=request.user.email)
            if leads_object.exists():
                if leads_object.first().company_registered_in != organization_info["country_name"]:
                    leads_object.update(company_registered_in=organization_info["country_name"])

            return Response({'message': 'OK', 'balance sheet': balance_sheet_response, 'profit loss': profit_loss,
                             'bank summary': bank_statement, "organization_info": organization_details,
                             'user_details': user_detail_serializer.data,
                             "country_name": organization_info["country_name"]},
                            status=status.HTTP_200_OK)
        else:
            return Response({'message': 'You do not have permission to perform this function'},
                            status=status.HTTP_400_BAD_REQUEST)


class XeroResponse(APIView):
    """
    class for getting xero response details
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.user_role == settings.SME['number_value']:
            is_xero_files_added = False
            if request.user.on_board_status == models.ON_BOARD_PASSWORD_SET and \
                    request.user.on_boarding_details is not None:
                is_xero_files_added = True
            user_detail = UserDetailSerializers(request.user.on_boarding_details).data
            leads_data = LeadsModelSerializers(
                instance=LeadsModel.objects.filter(company_email=request.user.email).last()).data
            return Response({"is_xero_files_added": is_xero_files_added, "user_detail": user_detail,
                             "country_name": leads_data["company_registered_in"]})
        else:
            return Response({'message': 'You do not have permission to perform this function'},
                            status=status.HTTP_400_BAD_REQUEST)


class OnBoardDataAPI(APIView):
    """
    class for onboard details
    """
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN['number_value']:
            # onboard details update entering
            user_details_dict = request.data
            user_details_object = get_object_or_404(models.UserDetailModel, pk=kwargs['user_id'])
            user_details_serializer = UserDetailSerializers(user_details_object, data=user_details_dict,
                                                            partial=True, context={"request": request})
            user_details_serializer.is_valid(raise_exception=True)
            user_details_serializer.save()
            contact_ids = []
            if request.data.get('additional_contact'):
                for contact_obj in eval(str(request.data['additional_contact'])):
                    if contact_obj.get('id'):
                        contact_object = models.UserContactDetails.objects.get(id=contact_obj['id'])
                        additional_contact_serializer = UserContactDetailsSerializers(contact_object,
                                                                                      contact_obj)
                        additional_contact_serializer.is_valid(raise_exception=True)
                        additional_contact_serializer.save()
                    else:
                        additional_contact_serializer = UserContactDetailsSerializers(
                            data=contact_obj, context={'user_details': user_details_object})
                        additional_contact_serializer.is_valid(raise_exception=True)
                        additional_contact_serializer.save()
                    contact_ids.append(additional_contact_serializer.data['id'])
            models.UserContactDetails.objects.filter(user_details=user_details_object).exclude(
                id__in=contact_ids).delete()
            response_dict = {'onboard': user_details_serializer.data}

            user_obj = models.User.objects.get(on_boarding_details=kwargs['user_id'])
            user_dict = {}
            if user_details_dict.get('first_name'):
                user_dict['first_name'] = user_details_dict['first_name']
            if user_details_dict.get('last_name'):
                user_dict['last_name'] = user_details_dict['last_name']
            if user_details_dict.get('credit_limit'):
                user_dict['credit_limit'] = user_details_dict['credit_limit']
            if user_dict:
                user_serializer = UserModelSerializers(user_obj, data=user_dict, partial=True,
                                                       context={"request": request})
                user_serializer.is_valid(raise_exception=True)
                user_serializer.save()

            # leads update entering
            leads_object = get_object_or_404(LeadsModel, sign_up_email=user_obj.email)
            leads_dict = user_details_dict
            if user_details_dict.get('country_name'):
                leads_dict['company_registered_in'] = user_details_dict.get('country_name')
            if leads_object.role not in [settings.SME["number_value"], settings.SUPPLIER["number_value"]]:
                return Response({'detail': 'Please check the role'}, status=status.HTTP_400_BAD_REQUEST)

            if leads_object.role == settings.SME["number_value"]:
                if not leads_object.invoice_amount and "invoice_amount" not in request.data:
                    return Response({"detail": "Please provide invoice_amount."}, status=status.HTTP_400_BAD_REQUEST)
                elif "invoice_amount" in request.data:
                    if int(request.data["invoice_amount"]) <= 0:
                        return Response({"detail": "Invoice amount should be greater than zero."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    else:
                        leads_dict["invoice_amount"] = request.data["invoice_amount"]
            if leads_dict.get("company_email") and leads_object.sign_up_email != leads_dict["company_email"]:
                leads_dict['sign_up_email'] = leads_dict["company_email"]
            if leads_dict.get('phone_number') and leads_object.sign_up_phone_number != leads_dict['phone_number']:
                leads_dict['sign_up_phone_number'] = leads_dict['phone_number']

            old_email = leads_object.sign_up_email
            leads_serializer_data = LeadsModelSerializers(leads_object, data=leads_dict, partial=True,
                                                          context={"request": request})
            leads_serializer_data.is_valid(raise_exception=True)
            leads_serializer_data.save()

            if "remarks" in request.data:
                lead_status_data = {'remarks': request.data["remarks"]}
                lead_status = LeadStatusModel.objects.get(id=leads_object.id)
                status_serializer_data = LeadStatusModelSerializers(lead_status, data=lead_status_data, partial=True)
                status_serializer_data.is_valid(raise_exception=True)
                status_serializer_data.save()

            response_dict['leads'] = leads_serializer_data.data
            return Response(response_dict, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'You do not have permission to perform this action'},
                            status=status.HTTP_400_BAD_REQUEST)


class OnBoardEmailAPI(ModelViewSet):
    """
    class for onboard details
    """
    permission_classes = [IsAuthenticated]

    # def get(self, request, *args, **kwargs):
    #     query_set = models.OnBoardEmailData.objects.filter(is_deleted=False)
    #     serializer_data = OnBoardEmailDataSerializers(query_set, many=True)
    #     return Response(serializer_data.data)

    queryset = models.OnBoardEmailData.objects.all()
    serializer_class = OnBoardEmailDataSerializers
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['^email']
    ordering_fields = ['email']
    pagination_class = PageNumberPagination
    pagination_class.page_size = 10


class SMEOnboardReviewMailListAPI(APIView):
    """
    Class for listing SME mails
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.user_role == settings.ADMIN["number_value"]:
            if 'user_onboard_id' not in request.data:
                return Response({'detail': 'please provide user on-board id.'}, status=status.HTTP_400_BAD_REQUEST)
            query_set = models.SMEOnBoardReviewEmailData.objects.filter(
                user_detail=request.data['user_onboard_id']).order_by("date_created")
        elif request.user.user_role == settings.SME["number_value"] and \
                request.user.on_board_status == models.ON_BOARD_IN_PROGRESS:
            query_set = models.SMEOnBoardReviewEmailData.objects.filter(
                user_detail=request.user.on_boarding_details.id).order_by("date_created")
        else:
            return Response({'detail': 'you dont have permission to perform this action.'},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = SMEOnboardReviewMailDataSerializer(query_set, many=True)
        return Response({'data': serializer.data}, status=status.HTTP_200_OK)


class CodatResponseAPI(APIView):
    """
    Class for codat response
    """

    def get(self, request, *args, **kwargs):
        if request.user.user_role == settings.SME["number_value"]:
            leads_obj = LeadsModel.objects.get(sign_up_email=request.user.email)
            leads_obj.sync_status = settings.SYNC_STARTED
            leads_obj.save()
            sync_state = codat_response(None, request.user, request, False)
            if sync_state == settings.NO_SYNC:
                leads_obj.sync_status = settings.NO_SYNC
                leads_obj.save()
            user_detail = UserDetailSerializers(request.user.on_boarding_details).data
            leads_data = LeadsModelSerializers(instance=leads_obj).data
            null_value_list = ["", None]
            if user_detail["contact_email"] in null_value_list:
                user_detail["contact_email"] = leads_data["company_email"]
            if user_detail["company_name"] in null_value_list:
                user_detail["company_name"] = leads_data["company_name"]
            if user_detail["company_telephone_number"] in null_value_list:
                user_detail["company_telephone_number"] = leads_data["phone_number"]    
            if user_detail["company_website"] in null_value_list:
                user_detail["company_website"] = leads_data["company_website"]       
            return Response({"sync_state": sync_state, "user_detail": user_detail,
                             'country_name': leads_data['company_registered_in']})


class UserPasswordResetView(APIView):
    """Class for reset password
    """

    def post(self, request):
        if 'email' not in request.data:
            return Response({
                "email": [
                    "This field is required."
                ]
            }, status=status.HTTP_400_BAD_REQUEST)

        user_object = get_object_or_404(models.User, email=request.data['email'], is_deleted=False)
        if user_object.on_board_status != models.ON_BOARD_USER_CREATED:
            password_reset_send_email(subject=settings.PASSWORD_RESET, model_instance=user_object,
                                      recipient_email=user_object.email)
            user_object.is_reset_password = True
            user_object.save()
            return Response({"message": "Successfully sent the password reset link to the user"},
                            status=status.HTTP_200_OK)
        else:
            return Response({"detail": "you cannot reset the password"},
                            status=status.HTTP_400_BAD_REQUEST)


class CodatDisconnectView(APIView):
    """Class for disconnecting codat
    """

    def post(self, request):
        if request.user.user_role == settings.SME["number_value"]:
            lead_object = get_object_or_404(LeadsModel, sign_up_email=request.user.email)
            for connections in codat_get_company_by_id(lead_object.company_id).get('dataConnections'):
                if 'id' in connections:
                    response = disconnect_codat(lead_object.company_id, connections['id'])
            if response.json():
                return Response({"message": "Successfully deleted the codat connection"},
                                status=status.HTTP_200_OK)
            else:
                return Response({"detail": "There is some error in disconnecting the codat"},
                                status=status.HTTP_200_OK)
        else:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)


class LogoutView(APIView):
    """Class for user logout
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        response = HttpResponseRedirect(request.data['domain'])
        response.delete_cookie('cookie_name')
        return Response({"detail": "Cookie removed succesfully"},
                                status=status.HTTP_200_OK)


class CodatVisualizeView(APIView):
    """Class for getting codat visualize uri
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        user_object = models.User.objects.get(on_boarding_details = request.data['on_board_id'])
        lead_object = get_object_or_404(LeadsModel, sign_up_email=user_object.email)
        codat_connection_respose = codat_get_company_by_id(lead_object.company_id).get('dataConnections')
        if 'id' in codat_connection_respose[0]:
            redirect_uri = settings.CODAT_URI + lead_object.company_id + '/dataConnection/' + codat_connection_respose[0].get("id")
        return Response({'redirect_uri': redirect_uri}, status=status.HTTP_200_OK)


class CodatStatus(APIView):
    """Class for getting codat visualize uri
    """
    permission_classes = [IsCustomAdminUser]

    def post(self, request):
        user_object = models.User.objects.get(on_boarding_details = request.data['on_board_id'])
        lead_object = get_object_or_404(LeadsModel, sign_up_email=user_object.email)
        connection_status = bool(codat_get_company_by_id(lead_object.company_id).get('dataConnections'))
        return Response({'connection_status': connection_status}, status=status.HTTP_200_OK)