from django.conf.urls import url

from .consumers import NotificationConsumer


websocket_urlpatterns = [
    url(r'^ws/notification/(?P<user_name>[^/]+)/$', NotificationConsumer),
]
