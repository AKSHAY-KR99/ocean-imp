# Generated by Django 3.2.3 on 2022-02-04 07:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0032_notificationmodel_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationmodel',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
    ]
