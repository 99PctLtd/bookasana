# Generated by Django 2.2a1 on 2019-02-10 00:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0002_periodicbooking'),
    ]

    operations = [
        migrations.AddField(
            model_name='periodicbooking',
            name='token_set',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
