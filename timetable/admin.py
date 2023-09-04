from django.contrib import admin
from .models import Center, CenterSchedule, ClassDetail


class ClassDetailAdmin(admin.ModelAdmin):
    list_display = ['date_time_field', 'start_time', 'class_name', 'teacher', 'location']
    ordering = ['-date_time_field', 'class_name']


admin.site.register(Center)
admin.site.register(CenterSchedule)
admin.site.register(ClassDetail, ClassDetailAdmin)