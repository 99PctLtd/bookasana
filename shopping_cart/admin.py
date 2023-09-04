from django.contrib import admin
from .models import OrderItem, Order, Transaction


class TransactionAdmin(admin.ModelAdmin):
    list_display = ['profile', 'timestamp', 'success']
    ordering = ['-timestamp', 'success', 'profile']


admin.site.register(OrderItem)
admin.site.register(Order)
admin.site.register(Transaction, TransactionAdmin)
