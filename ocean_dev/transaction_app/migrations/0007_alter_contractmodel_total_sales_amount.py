# Generated by Django 3.2.3 on 2021-11-03 04:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0006_alter_contractmodel_is_master_contract'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contractmodel',
            name='total_sales_amount',
            field=models.DecimalField(decimal_places=3, max_digits=20, null=True),
        ),
    ]
