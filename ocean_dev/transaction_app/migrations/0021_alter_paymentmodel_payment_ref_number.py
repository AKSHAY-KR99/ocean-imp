# Generated by Django 3.2.3 on 2022-01-07 08:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0020_contractmodel_additional_information'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentmodel',
            name='payment_ref_number',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
