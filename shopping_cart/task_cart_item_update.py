from account.models import Profile
from authentication.models import User
from booking_plan.models import BookingPlan
from shopping_cart.models import Order, OrderItem, Transaction
from shopping_cart.extra import generate_order_id

from celery import shared_task
from datetime import datetime


@shared_task()
def terminate_special_plan_and_unordered_item(plan_name=""):
    # plan_name = "Plan CNY"
    # terminate booking_plan
    booking_plans = BookingPlan.objects.filter(name=plan_name)
    if booking_plans.exists():
        booking_plan = booking_plans[0]
        booking_plan.is_valid = False
        booking_plan.save()

        # delete all unordered items
        order_items = OrderItem.objects.filter(
            product=booking_plan, is_ordered=False
        )
        if order_items.exists():
            for oi in order_items:
                oi.delete()
    else:
        print(f"{plan_name} : does not exist.")


# manually add order + order items to user account
# username="admin_ks"
# shopping_cart={
#     "Plan A": 4,
#     "Plan B": 1,
#     "Plan C": 0,
#     "Plan S - CNY 19": 1,
# }
def non_credit_card_transaction(username, shopping_cart):
    # create user order
    user = User.objects.get(username=username)
    profile = Profile.objects.get(user=user)
    order = Order.objects.create(
        owner=profile, is_ordered=True,
        ref_code=generate_order_id()
    )

    # create order items
    for sc in shopping_cart:
        if shopping_cart[sc] > 0:
            booking_plan = BookingPlan.objects.get(name=sc)
            OrderItem.objects.create(
                product=booking_plan, date_ordered=datetime.now(),
                is_ordered=True, item_quantity=shopping_cart[sc],
                order=order
            )

    # create transaction
    # token empty meaning it is non stripe/credit card transaction
    Transaction.objects.create(
        profile=profile,
        token="",
        order_id=order.id,
        amount=order.get_cart_price_total(),
        success=True,
    )

    # update user token number
    profile.token_single += order.get_cart_token_total()
    profile.save()
