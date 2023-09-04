from django.conf import settings
from django.contrib import admin
from django.conf.urls import url, include
from django.conf.urls.static import static
from . import views


urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^robots.txt$', views.robots, name='robots'),
    url(r'^faq/$', views.faq, name='faq'),
    url(r'^terms-of-service/$', views.terms_of_service, name='terms_of_service'),
    url(r'^privacy-policy/$', views.privacy_policy, name='privacy_policy'),
    url(r'^404/$', views.handler404, name='handler404'),
    url(r'^500/$', views.handler500, name='handler500'),

    url(r'^account/', include('account.urls')),
    url(r'^authentication/', include('authentication.urls')),
    url(r'^booking/', include('booking.urls')),
    url(r'^schedule/', include('timetable.urls')),
    url(r'^shopping_cart/', include('shopping_cart.urls')),

    url(r'^surya-namaskara-mies-login/', admin.site.urls),
    url(r'^', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
