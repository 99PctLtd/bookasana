# users/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import User


class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = [
        'username',
        'first_name',
        'last_name',
        'mobile_phone',
        'email',
        'pure_login',
        'pure_password',
        'email_confirmed',
        'agree_to_terms_privacy',
    ]


admin.site.register(User, CustomUserAdmin)
