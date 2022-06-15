# Generated by Django 3.2.3 on 2022-01-28 04:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0030_contracttypemodel_is_deleted'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='fundinvoicecountrymodel',
            options={'ordering': ['id']},
        ),
        migrations.AddField(
            model_name='fundinvoicecountrymodel',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='shipmentfilesmodel',
            name='country',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='shipment_country', to='transaction_app.fundinvoicecountrymodel'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='shipmentfilesmodel',
            name='document_type',
            field=models.CharField(choices=[(1, 'INVOICE'), (2, 'BL'), (3, 'AWB'), (4, 'PACKING_LIST'), (5, 'SGS_REPORT'), (6, 'ADDITIONAL_DOC')], default=1, max_length=200),
        ),
    ]
