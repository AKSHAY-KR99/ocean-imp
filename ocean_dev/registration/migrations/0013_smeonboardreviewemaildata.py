# Generated by Django 3.2.3 on 2022-03-02 11:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0012_user_approved_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='SMEOnBoardReviewEmailData',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254)),
                ('date_created', models.DateField(auto_now_add=True)),
                ('user_detail', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sme_review_sending_mails', to='registration.userdetailmodel')),
            ],
        ),
    ]
