from django.conf.urls import url
from shopping_cart import views

app_name = 'shopping_cart'

urlpatterns = [
    # /shopping_cart/top-up/
    url(r'^top-up/cancel-order/$',
        views.shopping_cancel_order, name='shopping_cancel_order'),
    url(r'^top-up/checkout-summary/$',
        views.shopping_checkout_summary, name='shopping_checkout_summary'),
    url(r'^top-up/delete-item/(?P<item_id>[0-9]+)/$',
        views.shopping_delete_item, name='shopping_delete_item'),
    url(r'^top-up/update-transaction-record/(?P<token>[-\w]+)/$',
        views.update_transaction_record, name='update_transaction_record'),
    url(r'^top-up/$',
        views.shopping_top_up, name='shopping_top_up'),
]
