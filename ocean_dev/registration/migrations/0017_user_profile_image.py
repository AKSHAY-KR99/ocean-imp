# Generated by Django 3.2.3 on 2022-05-05 05:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0016_user_is_reset_password'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='profile_image',
            field=models.ImageField(blank=True, null=True, upload_to=''),
        ),
    ]
