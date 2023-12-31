# Generated by Django 2.1.5 on 2019-01-13 22:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('account', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='membershiprecord',
            name='profile',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='account.Profile'),
        ),
        migrations.AddField(
            model_name='memberinfo',
            name='profile',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='account.Profile'),
        ),
        migrations.AddField(
            model_name='cookiejar',
            name='profile',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='account.Profile'),
        ),
        migrations.AddField(
            model_name='cookie',
            name='cookie_jar',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='account.CookieJar'),
        ),
    ]
