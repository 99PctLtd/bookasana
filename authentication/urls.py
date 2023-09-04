from . import views
from django.conf.urls import url
from django.contrib.auth.views import (
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView
)
from .views import MyPasswordResetView

app_name = 'authentication'

urlpatterns = [
    # # /authentication/
    url(r'^password/$', views.ChangePassword.as_view(), name='ChangePassword'),
    url(r'^edit-profile/$', views.EditProfile.as_view(), name='EditProfile'),
    url(r'^login/$', views.UserLogin.as_view(), name='login'),
    url(r'^logout/$', views.UserLogout.as_view(), name='logout'),
    url(r'^register/$', views.UserSignUp.as_view(), name='register'),

    # url(r'^reset-password/$', PasswordResetView.as_view(), name='password_reset'),
    url(r'^reset-password/$', MyPasswordResetView.as_view(), name='password_reset'),
    url(r'^reset-password/done/$', PasswordResetDoneView.as_view(), name='password_reset_done'),
    url(r'^reset-password/confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/$',
        PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    url(r'^account_activation_sent/$',
        views.account_activation_sent, name='account_activation_sent'),
    url(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.UserActivate.as_view(), name='activate'),
]