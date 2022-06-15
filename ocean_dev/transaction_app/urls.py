from . import views
from rest_framework import routers
from django.urls import path, include

router = routers.DefaultRouter()
router.register(r'fund/invoice', views.FundInvoiceViewSet)
# router.register(r'request/invoice', views.UploadInvoiceViewSet)
router.register(r'payment/terms', views.PaymentTermsViewSet)
router.register(r'contract', views.ContractTypeViewSet)
router.register(r'create/contract', views.ContractModelViewSet)
router.register(r'add/shipment', views.ShipmentModelViewSet)
router.register(r'amount/payment', views.PaymentViewSet)
router.register(r'account/details', views.AccountDetailsViewSet)
router.register(r'additional-cost', views.ContractAdditionalCostTypeViewset)
router.register(r'city/search', views.CityDetailsViewSet)
urlpatterns = [
    path('', include(router.urls)),
    path('request/<int:fund_invoice_id>/<slug:admin_action>/', views.RequestAdminApprovalView.as_view(),
         name="request_approval"),
    # path('request/supplier/invoice/', views.SendSupplierInvoiceRequestView.as_view(), name='supplier_invoice_upload'),
    # path('invoice/<int:request_id>/<slug:action>/', views.InvoiceApprovalView.as_view(), name="invoice_approval"),
    path('calculate/total-sales-amount/', views.CalculateSalesAmount.as_view(), name='calculate_total_sales_amount'),
    #path('send/contract/sme/', views.ContractSendToSme.as_view(), name='send_contract_sme'),
    path('approve/contract/sme/', views.ContractSMEApproval.as_view(), name='contract_sme_approval'),
    path('sign/contract/admin/', views.ContractAdminSign.as_view(), name='contract_admin_sign'),
    # path('acknowledge/contract/sme/', views.ContractSmeAcknowledgment.as_view(), name='acknowledge_contract_sme'),
    path('read/contract-file/', views.ReadContractFile.as_view(), name='read_contract_file'),
    path('user/payment/detail/', views.PaymentActionDetails.as_view(), name='user_payment_actions'),
    path('details/<int:fund_invoice_id>/payment/', views.GetInvoiceDetails.as_view(), name='payment_invoice_details'),
    path('acknowledge/shipment/<slug:user_action>/', views.ShipmentAcknowledgment.as_view(), name='acknowledge_shipment'),
    # path('shipment/admin/<slug:admin_action>/', views.ShipmentAdminApproval.as_view(), name='approve_shipment_admin'),
    # path('update/payment/status/', views.PaymentStatusUpdate.as_view(), name='update_payment_status'),
    path('acknowledge/payment/', views.PaymentAcknowledge.as_view(), name='acknowledge_payment'),
    path('generate/contract/sign/', views.GenerateDocSign.as_view(), name='doc_sign'),
    path('get/contract/doc/', views.GetSignedDoc.as_view(), name='get_signed_doc'),
    path('payment/invoice-listing/', views.PaymentInvoiceListing.as_view(), name='payment_invoice_listing'),
    path('shipment/file/upload/', views.ShipmentFileUpload.as_view(), name='shipment_file_upload'),
    path('delete/fund/invoice/<int:fund_invoice_id>/', views.DeleteFundInvoice.as_view(), name='delete_fund_invoice'),
    path('invoice/info/', views.FundInvoiceInfo.as_view(), name='fund_invoice_info'),
    path('send/reminder/mail/', views.SMEReminderMail.as_view(), name='sme_reminder_mail'),
    # path('city/search/', views.CityDetailsViewSet.as_view(), name='city_search'),
    path('delete/payment-term/<int:term_id>/', views.DeletePaymentTerm.as_view(), name='delete_supplier_term'),
    path('get/contract/number/', views.GetContractNumber.as_view(), name='get_contract_number'),
    path('get/notifications/', views.GetNotification.as_view(), name='notification_details'),
    path('delete/notification/<int:notification_id>/', views.DeleteNotification.as_view(), name="delete_notifications"),
    path('supplier/shipping/', views.SupplierShippingDetails.as_view(), name='supplier_shipping'),
    path('payment/history/<int:user_id>/', views.GetPaymentHistory.as_view(), name='payment_history'),
    path('calculate/over-due-amount/<int:fund_invoice>/', views.CalculateOverdueAmount.as_view(), name='calculate_overdue_amount')
]
