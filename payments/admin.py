from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("gateway_reference", "order", "amount", "currency", "status", "created_at")
    list_filter = ("status", "method")
    search_fields = ("gateway_reference", "gateway_transaction_id", "order__id")

    def get_readonly_fields(self, request, obj=None):
        # Payments are created and changed only by the payment code and the
        # audited refund API, never by hand in the admin.
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
