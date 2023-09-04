from django.db import models

from account.models import Profile
from booking_plan.models import BookingPlan
import uuid


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE)
    date_ordered = models.DateTimeField(auto_now=True)
    is_ordered = models.BooleanField(default=False)
    ref_code = models.CharField(max_length=15)

    def get_cart_items(self):
        item = ""
        for oi in self.orderitem_set.all().order_by("product__name"):
            if oi == self.orderitem_set.order_by("product__name").last():
                # item += oi.product.name + " x " + str(oi.item_quantity) + "."
                item += f"{oi.product.name} x {str(oi.item_quantity)}."
            else:
                item += oi.product.name + " x " + str(oi.item_quantity) + ", "
        return item

    def get_cart_item_total(self):
        return sum([item.item_quantity for item in self.orderitem_set.all()])

    def get_cart_token_total(self):
        return sum([(item.product.token_single * item.item_quantity) for item in self.orderitem_set.all()])

    def get_cart_price_total(self):
        return sum([(item.product.price * item.item_quantity) for item in self.orderitem_set.all()])

    def __str__(self):
        return '{0} - {1}, {2}'.format(self.ref_code, self.is_ordered, self.owner.user.username)


class OrderItem(models.Model):
    product = models.ForeignKey(BookingPlan, on_delete=models.CASCADE)
    date_added = models.DateTimeField(auto_now=True)
    date_ordered = models.DateTimeField(null=True)
    is_ordered = models.BooleanField(default=False)
    item_quantity = models.PositiveSmallIntegerField(default=0)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return '{0} - {1}'.format(self.product.name, self.is_ordered)

    def get_order_item_price_total(self):
        return self.product.price * self.item_quantity

    def get_order_item_token_total(self):
        return self.product.token_single * self.item_quantity


class Transaction(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    token = models.CharField(max_length=120)
    order_id = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    success = models.BooleanField(default=True)
    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)

    def __str__(self):
        return self.profile.user.username + " - " + self.order_id

    class Meta:
        ordering = ['-timestamp']