from django.contrib import admin
from .models import AdminUser


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "role", "is_active", "created_at")
    search_fields = ("name", "email")
    list_filter = ("role", "is_active")
