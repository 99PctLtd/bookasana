from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    UserChangeForm,
    PasswordResetForm,
)
from django.urls import reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.safestring import mark_safe
from django.utils.http import urlsafe_base64_encode

from .email_utils import send_grid_email
from .models import User
from .tokens import account_activation_token


class CustomUserActivationForm(UserChangeForm):
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    pure_login = forms.EmailField(max_length=254,
                                  help_text='required. valid Pure login/email '
                                            'is essential for syncing class info '
                                            'and registration.',)
    pure_password = forms.CharField(widget=forms.PasswordInput,
                                    help_text='required. valid Pure password '
                                              'is essential for syncing class info '
                                              'and registration.',)

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'mobile_phone',
            'pure_login',
            'pure_password',
        )


class CustomUserCreationForm(UserCreationForm):
    pure_login = forms.EmailField(max_length=254,
                                  help_text='Required. Valid Pure Login/Email '
                                            'is essential for registration.')
    agree_to_terms_privacy = forms.BooleanField(
        required=True,
        label=mark_safe("I agree to bookasana's "
                        "<a href='/terms-of-service' target='_blank'>"
                        "<strong>[ terms of service ]</strong></a>"
                        " and <a href='/privacy-policy' target='_blank'>"
                        "<strong>[ privacy policy ]</strong></a>."),
        error_messages={"invalid": "You must agree to use our service."}
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            'username',
            'pure_login',
            'password1',
            'password2',
            'agree_to_terms_privacy',
        )


class CustomUserChangeForm(UserChangeForm):
    pure_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'mobile_phone',
            'pure_login',
            'pure_password'
        )


class EditProfileForm(UserChangeForm):
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    mobile_phone = forms.CharField(required=False)
    pure_login = forms.EmailField(max_length=254,
                                  help_text='Required. Valid Pure Login/Email '
                                            'is essential.')
    pure_password = forms.CharField(widget=forms.PasswordInput,
                                    required=False,
                                    help_text='Leave blank if no change is necessary.',
                                    )

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'mobile_phone',
            'pure_login',
            'pure_password',
        )


class MyPasswordResetForm(PasswordResetForm):

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        user = context['user']
        send_grid_email(
            {
                'user': user,
                'protocol': context['protocol'],
                'domain': context['domain'],
                'uid_token': reverse_lazy(
                    'authentication:password_reset_confirm',
                    kwargs={
                        'uidb64': context['uid'],
                        'token': context['token'],
                    }
                ),
            },
            password_reset=True,
        )

    def my_get_user(self, email):
        return User.objects.get(email=email, is_active=True)

