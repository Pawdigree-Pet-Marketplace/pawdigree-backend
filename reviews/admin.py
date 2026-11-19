from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "rating", "product", "service", "pet", "is_visible", "created_at")
    list_filter = ("is_visible", "rating")
    search_fields = ("comment", "customer__email")
