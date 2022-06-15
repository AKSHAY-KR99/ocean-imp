# Generated by Django 3.2.3 on 2021-12-01 09:42

from django.db import migrations, models
import utils.model_utility


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0006_user_is_xero_files_added'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_name',
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_physical_address',
            field=models.TextField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_registered_address',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_registration_id',
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_telephone_number',
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='company_website',
            field=models.URLField(null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='contact_email',
            field=models.EmailField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='contact_mobile_phone',
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='contact_person',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='contact_person_designation',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='current_balance_sheet',
            field=models.FileField(blank=True, help_text='Current balance sheet', null=True, upload_to=utils.model_utility.user_detail_base_path),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='last_bank_statements',
            field=models.FileField(blank=True, help_text='Last 3 months Bank statements', null=True, upload_to=utils.model_utility.user_detail_base_path),
        ),
        migrations.AlterField(
            model_name='userdetailmodel',
            name='last_year_profit_loss',
            field=models.FileField(blank=True, help_text='Last 12 months profit/loss', null=True, upload_to=utils.model_utility.user_detail_base_path),
        ),
    ]