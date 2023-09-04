from django.conf import settings
from django.db import models
from django.db.models.signals import post_save


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    acc_valid = models.BooleanField(default=True)

    client_id = models.CharField(max_length=15, null=True, blank=True)
    membership_exp_fitness = models.DateField(null=True, blank=True)
    membership_exp_special = models.DateField(null=True, blank=True)
    membership_exp_yoga = models.DateField(null=True, blank=True)
    membership_ref_fitness = models.CharField(max_length=15, null=True, blank=True)
    membership_ref_special = models.CharField(max_length=15, null=True, blank=True)
    membership_ref_yoga = models.CharField(max_length=15, null=True, blank=True)
    membership_type_fitness = models.CharField(max_length=254, null=True, blank=True)
    membership_type_special = models.CharField(max_length=254, null=True, blank=True)
    membership_type_yoga = models.CharField(max_length=254, null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=10)
    token_single = models.SmallIntegerField(default=5)

    def __str__(self):
        return self.user.username + " has " + str(self.token_single) + " tokens."

    def get_token_needed(self):
        token_needed = 0
        for booking in self.bookingrecord_set.first().booking_set.all():
            if booking.is_listed:
                token_needed += booking.token_used
        return token_needed


class MembershipRecord(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True)
    paid_date = models.DateField(null=True, blank=True)
    payment_ref = models.CharField(max_length=15, null=True, blank=True)
    amount = models.CharField(max_length=15, null=True, blank=True)
    description = models.CharField(max_length=254, null=True, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    available = models.BooleanField(default=False)

    def __str__(self):
        return self.profile.user.username + " : " + self.payment_ref + ", " + str(self.exp_date) + ", " + self.description


class MemberInfo(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(max_length=254, null=True, blank=True)
    address = models.CharField(max_length=254, null=True, blank=True)
    birthday = models.DateField(null=True, blank=True)
    cellphone = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.profile.user.username + " : " + self.name


class CookieJar(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True)
    cookie_csrf = models.CharField(max_length=24)
    date_time_field = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "cookie " + str(self.date_time_field) + " - " + self.profile.user.username


class Cookie(models.Model):
    cookie_jar = models.ForeignKey(CookieJar, on_delete=models.CASCADE)
    cookie_name = models.CharField(max_length=32)
    cookie_value = models.CharField(max_length=2048)

    def __str__(self):
        return self.cookie_name + " : " + self.cookie_value


def post_save_profile_create(sender, instance, created, *args, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


post_save.connect(post_save_profile_create, sender=settings.AUTH_USER_MODEL)