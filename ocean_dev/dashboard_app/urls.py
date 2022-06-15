from django.urls import path
from . import views

urlpatterns = [
    # path('leads-yearly-info/', views.DashboardYearlyLeadsInfo.as_view(), name="leads_yearly_info"),
    path('funds-info/', views.DashboardFundsInfo.as_view(), name="funds_info"),
    # path('funds-yearly-info/', views.DashboardYearlyFundsInfo.as_view(), name="funds_yearly_info"),
    path('transactions-info/', views.DashboardTransactionsInfo.as_view(), name="transactions_info"),
    path('sme/info/', views.DashboardSmeInfo.as_view(), name="sme_info"),
    path('invoice/overview/', views.DashboardInvoiceRequestOverview.as_view(), name="fund_request_overview"),
    path('supplier/payment/info/', views.DashboardSupplierPaymentInfo.as_view(), name="supplier-payment-info"),
    path('sme/payment/info/', views.DashboardSmePaymentInfo.as_view(), name="sme_info"),
    path('leads-conversion-info/', views.DashboardLeadsConversionInfo.as_view(), name="leads_conversion_info"),
    path('supplier/monthly/payment/', views.DashboardSupplierToPaymentInfo.as_view(), name="supplier-monthly-payment-info"),
    path('admin/sme/info/', views.AdminDashboardinfo.as_view(), name="admin_sme_info")
]
