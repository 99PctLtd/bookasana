# Generated by Django 2.2a1 on 2019-02-09 22:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0003_auto_20190206_1514'),
    ]

    operations = [
        migrations.AlterField(
            model_name='classdetail',
            name='duration',
            field=models.CharField(max_length=10),
        ),
        migrations.AlterField(
            model_name='classdetail',
            name='start_time',
            field=models.CharField(max_length=5),
        ),
    ]
