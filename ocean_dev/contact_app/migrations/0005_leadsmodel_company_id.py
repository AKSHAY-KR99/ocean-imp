# Generated by Django 3.2.3 on 2022-04-11 10:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact_app', '0004_alter_leadsmodel_invoice_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadsmodel',
            name='company_id',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]