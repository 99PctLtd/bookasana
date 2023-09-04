from django.contrib import admin
from .models import Booking, BookingRecord, PeriodicBooking


class BookingAdmin(admin.ModelAdmin):
    list_display = ['booking_record', 'class_item', 'token_used', 'date_added']
    ordering = ['-date_added', 'class_item']


class BookingRecordAdmin(admin.ModelAdmin):
    list_display = ['owner', 'waitlist_update_time', 'schedule_update_time']
    ordering = ['owner']


class PeriodicBookingAdmin(admin.ModelAdmin):
    list_display = ['week_day_django', 'start_time', 'class_name', 'teacher', 'location', 'token_set', 'booking_record']
    ordering = ['week_day_django', 'start_time', 'booking_record__owner']


admin.site.register(Booking, BookingAdmin)
admin.site.register(BookingRecord, BookingRecordAdmin)
admin.site.register(PeriodicBooking, PeriodicBookingAdmin)

