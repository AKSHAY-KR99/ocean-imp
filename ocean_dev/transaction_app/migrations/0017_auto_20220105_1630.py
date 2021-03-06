# Generated by Django 3.2.3 on 2022-01-05 11:00

from django.db import migrations, models
import django.db.models.deletion
import django_countries.fields


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0016_auto_20211125_1629'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fundinvoicemodel',
            name='destination_country',
        ),
        migrations.AlterField(
            model_name='contractmodel',
            name='contract_number',
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.CreateModel(
            name='FundInvoiceCountryModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shipping_date', models.DateField(blank=True, null=True)),
                ('origin_country', django_countries.fields.CountryField(max_length=2)),
                ('destination_country', django_countries.fields.CountryField(max_length=2)),
                ('fund_invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fund_invoice_country', to='transaction_app.fundinvoicemodel')),
            ],
            options={
                'ordering': ['-id'],
            },
        ),
    ]
