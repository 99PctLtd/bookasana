from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.generic import TemplateView

from account.models import Profile
from booking_plan.models import BookingPlan
from .extra import generate_order_id
from .forms import OrderItemForm
from .models import Order, OrderItem, Transaction
from booking.views import update_token_balance_status

from datetime import datetime
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY


def get_user_pending_order(request):
    # get order for the correct user
    user_profile = get_object_or_404(Profile, user=request.user)
    order = Order.objects.filter(owner=user_profile, is_ordered=False)
    if order.exists():
        # get the only order in the list of filtered orders
        return order[0]
    return 0


@login_required()
def shopping_cancel_order(request):
    # get the user profile
    user_profile = get_object_or_404(Profile, user=request.user)
    order = Order.objects.filter(owner=user_profile, is_ordered=False)
    if order.exists():
        order[0].delete()
    return redirect('shopping_cart:shopping_top_up')


@login_required()
def shopping_checkout_summary(request):
    user_order = get_user_pending_order(request)
    publish_key = settings.STRIPE_PUBLISHABLE_KEY

    if user_order:
        if request.method == 'POST':
            try:
                token = request.POST['stripeToken']

                charge = stripe.Charge.create(
                    amount=int(100 * user_order.get_cart_price_total()),
                    currency='hkd',
                    description="Charge for " + user_order.owner.user.username,
                    source=token,
                )
                return redirect(reverse('shopping_cart:update_transaction_record',
                                        kwargs={
                                            'token': token,
                                        })
                                )
            except stripe.error.CardError as e:
                token = request.POST['stripeToken']
                transaction = Transaction.objects.create(
                    profile=request.user.profile,
                    token=token,
                    order_id=user_order.id,
                    amount=user_order.get_cart_price_total(),
                    success=False,
                )
                transaction.save()
                messages.info(request, "Your card has been declined.")

        order_items = OrderItem.objects.filter(order=user_order,
                                               is_ordered=False).order_by("product__name")
        content = {
            "order": user_order,
            "order_items": order_items,
            'STRIPE_PUBLISHABLE_KEY': publish_key,
        }
        return render(request, 'shopping_cart/checkout_summary.html', content)
    else:
        return redirect(reverse('shopping_cart:shopping_top_up'))


@login_required()
def shopping_delete_item(request, item_id):
    order_item = OrderItem.objects.filter(id=item_id)
    # check if item exists
    if order_item.exists():
        # check if item belongs to user
        if request.user == order_item[0].order.owner.user:
            order_item[0].delete()
            shopping_order_check(request)
        else:
            messages.info(request, "error: you don't have permission to delete such item.")
    else:
        messages.info(request, "error: no such item.")
    return redirect('shopping_cart:shopping_top_up')


@login_required()
def shopping_order_check(request):
    # get the user profile
    user_profile = get_object_or_404(Profile, user=request.user)
    order = Order.objects.filter(owner=user_profile, is_ordered=False)
    if order.exists():
        if not OrderItem.objects.filter(order=order[0]).exists():
            order[0].delete()
    pass


@login_required()
def shopping_top_up(request):
    # get the user profile
    user_profile = get_object_or_404(Profile, user=request.user)

    if request.method == 'POST':
        # oi_forms = [OrderItemForm(request.POST, prefix=str(x), instance=OrderItem())
        #             for x in range(0, BookingPlan.objects.count())]
        oi_forms = [OrderItemForm(request.POST, prefix=str(x), instance=OrderItem())
                    for x in range(0, BookingPlan.objects.filter(is_valid=True).count())]
        if all([oi.is_valid() for oi in oi_forms]):
            # get_or_create order associated with the user
            user_order, created = Order.objects.get_or_create(owner=user_profile,
                                                              is_ordered=False)
            # save form input to database
            # booking_plans = [bp for bp in BookingPlan.objects.all()]
            booking_plans = [bp for bp in BookingPlan.objects.filter(is_valid=True).order_by("name")]
            for oi, booking_plan in zip(oi_forms, booking_plans):
                # check if order exist for user
                if created:
                    # create item if quantity > 0
                    if oi.cleaned_data['item_quantity'] > 0:
                        new_oi = oi.save(commit=False)
                        new_oi.product = booking_plan
                        new_oi.order = user_order
                        new_oi.item_quantity = oi.cleaned_data['item_quantity']
                        new_oi.save()
                    # generate order reference number
                    user_order.ref_code = generate_order_id()
                    user_order.save()
                else:
                    # update item if quanity > 0
                    if oi.cleaned_data['item_quantity'] > 0:
                        if OrderItem.objects.filter(order=user_order,
                                                    product=booking_plan,
                                                    is_ordered=False).exists():
                            exist_oi = OrderItem.objects.get(order=user_order,
                                                             product=booking_plan,
                                                             is_ordered=False)
                            exist_oi.item_quantity = exist_oi.item_quantity + oi.cleaned_data['item_quantity']
                            exist_oi.save()
                        else:
                            new_oi = oi.save(commit=False)
                            new_oi.product = booking_plan
                            new_oi.order = user_order
                            new_oi.item_quantity = oi.cleaned_data['item_quantity']
                            new_oi.save()
            # delete order if order item quantity is 0
            if not OrderItem.objects.filter(order=user_order, is_ordered=False).exists():
                user_order.delete()
                user_order = None

            oi_forms = [OrderItemForm(prefix=str(x), instance=OrderItem())
                        for x in range(0, BookingPlan.objects.count())]
            # plans_ois = zip(BookingPlan.objects.all(), oi_forms)
            plans_ois = zip(BookingPlan.objects.filter(is_valid=True).order_by("name"), oi_forms)
            order_items = OrderItem.objects.filter(order=user_order,
                                                   is_ordered=False).order_by("product__name")
            content = {
                "date_today": datetime.today().strftime('%d %b %y, %a'),
                "order": user_order,
                "order_items": order_items,
                "plans_ois": plans_ois,
                "user_profile": user_profile,
            }
            return render(request, 'shopping_cart/top_up.html', content)
    else:
        # oi_forms = [OrderItemForm(prefix=str(x), instance=OrderItem())
        #             for x in range(0, BookingPlan.objects.count())]
        oi_forms = [OrderItemForm(prefix=str(x), instance=OrderItem())
                    for x in range(0, BookingPlan.objects.filter(is_valid=True).count())]
        # return current order if exists
        if Order.objects.filter(owner=user_profile, is_ordered=False).exists():
            user_order = Order.objects.get(owner=user_profile, is_ordered=False)
            order_items = OrderItem.objects.filter(order=user_order,
                                                   is_ordered=False).order_by("product__name")
        else:
            user_order = None
            order_items = None
        # plans_ois = zip(BookingPlan.objects.all(), oi_forms)
        plans_ois = zip(BookingPlan.objects.filter(is_valid=True).order_by("name"), oi_forms)
        content = {
            "date_today": datetime.today().strftime('%d %b %y, %a'),
            "order": user_order,
            "order_items": order_items,
            "plans_ois": plans_ois,
            "user_profile": user_profile,
        }
        return render(request, 'shopping_cart/top_up.html', content)


@login_required()
def update_transaction_record(request, token):
    # get the order being processed
    order = get_user_pending_order(request)
    # update processed order
    order.date_ordered = datetime.now()
    order.is_ordered = True
    order.save()
    # update processed order item
    order_items = OrderItem.objects.filter(order=order)
    for oi in order_items:
        oi.date_ordered = datetime.now()
        oi.is_ordered = True
        oi.save()

    # update user token number
    profile = Profile.objects.filter(user=request.user).first()
    profile.token_single += order.get_cart_token_total()
    profile.save()

    transaction = Transaction.objects.create(
        profile=profile,
        token=token,
        order_id=order.id,
        amount=order.get_cart_price_total(),
        success=True,
    )
    transaction.save()

    if order.get_cart_token_total() == 1:
        messages.success(request, "Transaction completed, " + str(order.get_cart_token_total()) +
                                  " token has been added to your account.")
    else:
        messages.success(request, "Transaction completed, " + str(order.get_cart_token_total()) +
                                  " tokens have been added to your account.")
    return redirect('account:my_info')
