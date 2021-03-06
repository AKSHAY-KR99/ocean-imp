# Generated by Django 3.2.3 on 2022-04-20 08:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0013_smeonboardreviewemaildata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_physical_address',
            field=models.TextField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_registered_address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_registration_id',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_telephone_number',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_website',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='contact_email',
            field=models.EmailField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='contact_mobile_phone',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
