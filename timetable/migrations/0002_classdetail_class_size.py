# Generated by Django 2.2a1 on 2019-02-04 21:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='classdetail',
            name='class_size',
            field=models.PositiveSmallIntegerField(default=30),
        ),
    ]
