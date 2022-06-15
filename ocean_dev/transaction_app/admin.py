from django.contrib import admin
from . import models

# Register your models here.

admin.site.register(models.FundInvoiceModel)
admin.site.register(models.FundInvoiceFilesModel)
admin.site.register(models.FundInvoiceStatusModel)


class FundInvoiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'origin_city', 'destination_city', 'shipment_mode', 'shipping_date']
    list_filter = ['shipment_mode', 'shipping_date']
    search_fields = ['origin_city__display_name', 'destination_city__display_name',
                     'origin_country__name', 'destination_country__name', 'fund_invoice__invoice_number']


admin.site.register(models.FundInvoiceCountryModel, FundInvoiceAdmin)
admin.site.register(models.SmeTermsAmountModel)
admin.site.register(models.SmeTermsInstallmentModel)
admin.site.register(models.SupplierTermsModel)
admin.site.register(models.PaymentTermModel)
admin.site.register(models.ContractTypeModel)
admin.site.register(models.ContractModel)
admin.site.register(models.SignedContractFilesModel)
admin.site.register(models.ShipmentModel)
admin.site.register(models.ShipmentFilesModel)
admin.site.register(models.PaymentModel)
admin.site.register(models.PaymentFilesModel)
admin.site.register(models.PaymentStatusModel)
admin.site.register(models.MasterContractStatusModel)
admin.site.register(models.AccountDetailsModel)
admin.site.register(models.ContractAdditionalCostType)
admin.site.register(models.AdditionalContractCost)
admin.site.register(models.NotificationModel)
