# Generated by Django 2.2a1 on 2019-02-05 21:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking_plan', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='bookingplan',
            name='is_valid',
            field=models.BooleanField(default=False),
        ),
    ]
