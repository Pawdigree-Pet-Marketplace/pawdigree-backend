from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("gateway_reference", "order", "amount", "currency", "status", "created_at")
    list_filter = ("status", "method")
    search_fields = ("gateway_reference", "gateway_transaction_id", "order__id")
    readonly_fields = ("gateway_payload",)
