# Generated by Django 3.2.3 on 2022-01-13 06:54

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_app', '0025_auto_20220112_1544'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContractAdditionalCostType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('additional_cost_type', models.CharField(max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='AdditionalContractCost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('additional_cost_value', models.DecimalField(decimal_places=3, max_digits=10)),
                ('additional_cost_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='additional_contract_cost_type', to='transaction_app.contractadditionalcosttype')),
                ('contract', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='additional_contract_cost', to='transaction_app.contractmodel')),
            ],
        ),
    ]
