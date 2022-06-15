# Generated by Django 3.2.3 on 2022-01-18 04:02

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contact_app', '0004_alter_leadsmodel_invoice_amount'),
        ('registration', '0008_remove_user_is_xero_files_added'),
        ('transaction_app', '0026_additionalcontractcost_contractadditionalcosttype'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_read', models.BooleanField(default=False)),
                ('notification', models.TextField(max_length=100)),
                ('type', models.CharField(max_length=50)),
                ('description', models.TextField(max_length=100)),
                ('is_completed', models.BooleanField(default=False)),
                ('assignee', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_user', to=settings.AUTH_USER_MODEL)),
                ('contract', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_contract', to='transaction_app.contractmodel')),
                ('fund_invoice', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_fund_invoice', to='transaction_app.fundinvoicemodel')),
                ('lead_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lead_user_notification', to='contact_app.leadsmodel')),
                ('shipment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_shipment', to='transaction_app.shipmentmodel')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user_notification', to=settings.AUTH_USER_MODEL)),
                ('user_detail', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user_details', to='registration.userdetailmodel')),
            ],
        ),
    ]