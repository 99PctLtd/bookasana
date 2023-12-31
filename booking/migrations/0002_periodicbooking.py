# Generated by Django 2.2a1 on 2019-02-09 22:41

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PeriodicBooking',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('start_time', models.CharField(max_length=5)),
                ('class_name', models.CharField(max_length=100)),
                ('teacher', models.CharField(max_length=50)),
                ('location', models.CharField(max_length=100)),
                ('week_day_django', models.PositiveSmallIntegerField(default=0)),
                ('booking_record', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='booking.BookingRecord')),
            ],
        ),
    ]
