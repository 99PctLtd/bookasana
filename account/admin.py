from django.contrib import admin
from .models import Profile, MembershipRecord, MemberInfo, CookieJar, Cookie


class FlatPageAdmin(admin.ModelAdmin):
    fields = ('user', 'client_id', 'priority', 'token_single',
              'membership_ref_fitness', 'membership_type_fitness',
              'membership_exp_fitness', 'membership_ref_yoga',
              'membership_type_yoga', 'membership_exp_yoga',
              'membership_ref_special', 'membership_type_special',
              'membership_exp_special',)


class CookieJarAdmin(admin.ModelAdmin):
    list_display = ['profile', 'cookie_csrf', 'date_time_field']
    ordering = ['profile']


class MembershipRecordAdmin(admin.ModelAdmin):
    list_display = ['profile', 'description', 'payment_ref', 'exp_date', 'available']
    ordering = ['-available', '-exp_date', 'profile', 'description']


class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'acc_valid', 'priority', 'token_single']
    ordering = ['priority', 'user']


admin.site.register(CookieJar, CookieJarAdmin)
admin.site.register(Cookie)
admin.site.register(MembershipRecord, MembershipRecordAdmin)
admin.site.register(MemberInfo)
admin.site.register(Profile, ProfileAdmin)

