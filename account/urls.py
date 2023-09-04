from django.conf.urls import url
from . import views

app_name = 'account'

urlpatterns = [
    # /account/20180401/
    url(r'^info/transaction_summary_single/(?P<order_id>[0-9A-Za-z_\-]+)/$',
        views.transaction_summary_single, name='transaction_summary_single'),
    url(r'^info/$', views.my_info, name='my_info'),
    url(r'^transaction_history/$', views.transaction_history, name='transaction_history'),
]
