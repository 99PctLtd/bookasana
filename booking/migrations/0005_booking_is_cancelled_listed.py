# Generated by Django 2.2a1 on 2019-02-10 22:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_periodicbooking_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='is_cancelled_listed',
            field=models.BooleanField(default=False),
        ),
    ]
