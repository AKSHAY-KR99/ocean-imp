# Generated by Django 3.2.3 on 2022-01-06 05:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0018_auto_20220105_1759'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymenttermmodel',
            name='is_delete',
            field=models.BooleanField(default=False),
        ),
    ]
