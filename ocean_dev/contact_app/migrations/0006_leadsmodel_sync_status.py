# Generated by Django 3.2.3 on 2022-04-18 07:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact_app', '0005_leadsmodel_company_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadsmodel',
            name='sync_status',
            field=models.CharField(default='no_sync', max_length=100),
        ),
    ]
