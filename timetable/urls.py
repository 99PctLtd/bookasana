from django.conf.urls import url
from . import views

app_name = 'schedule'

urlpatterns = [
    # /schedule/hong kong/yoga/
    url(r'^schedule-current/$', views.schedule_current, name='schedule_current'),
    url(r'^schedule/$', views.schedule, name='schedule'),
]
