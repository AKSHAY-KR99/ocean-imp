# Generated by Django 3.2.3 on 2021-10-06 10:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadsmodel',
            name='invoice_amount',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=20),
        ),
    ]
