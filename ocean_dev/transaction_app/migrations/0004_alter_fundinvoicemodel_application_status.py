# Generated by Django 3.2.7 on 2021-10-28 09:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0003_fundinvoicemodel_destination_country'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fundinvoicemodel',
            name='application_status',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, 'INITIATED'), (2, 'APPROVED'), (3, 'REJECTED')], null=True),
        ),
    ]