# Generated by Django 3.2.3 on 2022-01-20 12:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0028_rename_user_detail_notificationmodel_on_boarding_details'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fundinvoicecountrymodel',
            name='shipment_mode',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, 'AIR'), (2, 'SEA')], null=True),
        ),
    ]
