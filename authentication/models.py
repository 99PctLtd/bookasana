from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):

    agree_to_terms_privacy = models.BooleanField(default=False)
    email_confirmed = models.BooleanField(default=False)
    mobile_phone = models.CharField(max_length=15, null=True, blank=True, unique=True)
    pure_login = models.EmailField(max_length=254, null=True, unique=True)
    pure_password = models.CharField(max_length=254, null=True)

    def __str__(self):
        return self.username + " - " + self.last_name + ", " + self.first_name

