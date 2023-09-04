from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from account.models import Profile
from shopping_cart.models import Order, OrderItem

from datetime import date


@login_required()
def get_user_profile(request):
    user_profile = get_object_or_404(Profile, user=request.user)
    return user_profile


@login_required()
def transaction_history(request):
    user_profile = get_user_profile(request)
    user_order = Order.objects.filter(
        owner=user_profile,
        is_ordered=True
    ).order_by("date_ordered").reverse()
    content = {
        'user_order': user_order,
        'user_profile': user_profile,
    }
    return render(request, 'account/transaction_history.html', content)


@login_required()
def transaction_summary_single(request, order_id):
    user_profile = get_object_or_404(Profile, user=request.user)
    user_order = Order.objects.filter(owner=user_profile, id=order_id)
    if user_order.exists():
        order_items = OrderItem.objects.filter(order=user_order[0],
                                               is_ordered=True).order_by("product__name")
        content = {
            "order": user_order[0],
            "order_items": order_items,
        }
        return render(request, 'account/transaction_summary_single.html', content)
    else:
        messages.info(request, "You don't have such transaction.")
    return redirect('account:my_info')


@login_required()
def my_info(request):
    user_profile = get_user_profile(request)
    user_order = Order.objects.filter(
        owner=user_profile,
        is_ordered=True
    ).order_by("date_ordered").reverse()
    content = {
        'date_today': date.today(),
        'user_order': user_order[0:5],
        'user_order_count': user_order.count(),
        'user_profile': user_profile,
    }
    return render(request, 'account/info.html', content)
