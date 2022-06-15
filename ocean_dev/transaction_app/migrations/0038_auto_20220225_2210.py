# Generated by Django 3.2.3 on 2022-02-25 16:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0037_auto_20220225_1929'),
    ]

    operations = [
        migrations.AddField(
            model_name='fundinvoicemodel',
            name='gross_margin',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name='fundinvoicemodel',
            name='markup',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True),
        ),
    ]
