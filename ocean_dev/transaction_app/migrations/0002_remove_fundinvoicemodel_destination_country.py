# Generated by Django 3.2.3 on 2021-10-06 07:26

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fundinvoicemodel',
            name='destination_country',
        ),
    ]