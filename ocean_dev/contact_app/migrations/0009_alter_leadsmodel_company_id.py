# Generated by Django 3.2.3 on 2022-05-23 11:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact_app', '0008_leadsmodel_is_mail_send'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leadsmodel',
            name='company_id',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
