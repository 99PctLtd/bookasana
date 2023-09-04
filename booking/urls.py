from . import views
from django.contrib.auth.decorators import login_required
from django.conf.urls import url

app_name = 'booking'

urlpatterns = [
    # /booking/20180401/
    url(r'^add-to-repeat-weekly/(?P<booking_id>[0-9A-Za-z_\-]+)/$',
        views.add_to_repeat_weekly, name='add_to_repeat_weekly'),
    url(r'^add-to-selection-schedule/(?P<class_id>[0-9A-Za-z_\-]+)/$',
        views.add_to_selection_schedule, name='add_to_selection_schedule'),
    url(r'^confirm-selection-all/$',
        views.confirm_selection_all, name='confirm_selection_all'),
    url(r'^confirm-selection-single/(?P<booking_id>[0-9A-Za-z_\-]+)/$',
        views.confirm_selection_single, name='confirm_selection_single'),
    url(r'^delete-from-booked/(?P<booking_id>[0-9A-Za-z_\-]+)/$',
        views.delete_from_booked, name='delete_from_booked'),
    url(r'^delete-from-list-info/(?P<booking_id>[0-9A-Za-z_\-]+)/$',
        views.delete_from_list_info, name='delete_from_list_info'),
    url(r'^delete-from-repeat-weekly/(?P<periodic_booking_id>[0-9A-Za-z_\-]+)/$',
        views.delete_from_repeat_weekly, name='delete_from_repeat_weekly'),
    url(r'^delete-from-selection-info/(?P<booking_id>[0-9A-Za-z_\-]+)/$',
        views.delete_from_selection_info, name='delete_from_selection_info'),
    url(r'^delete-from-selection-schedule/(?P<class_id>[0-9A-Za-z_\-]+)/$',
        views.delete_from_selection_schedule, name='delete_from_selection_schedule'),
    url(r'^delete-from-waitlist-info/(?P<booking_id>[0-9A-Za-z_\-]+)/$',
        views.delete_from_waitlist_info, name='delete_from_waitlist_info'),

    url(r'^class/$', login_required(views.MyClass.as_view()), name='my_class'),
    url(r'^history/$', views.my_history, name='my_history'),
]
