from django.db import models


class BookingPlan(models.Model):
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=5, decimal_places=1)
    token_single = models.PositiveSmallIntegerField()
    is_valid = models.BooleanField(default=False)

    def __str__(self):
        return self.name + " : " + str(self.token_single) + " tokens"

