# Generated by Django 3.2.3 on 2022-02-25 05:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0011_usercontactdetails'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='approved_by',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
    ]