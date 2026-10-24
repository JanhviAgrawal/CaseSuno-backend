
from django.contrib import admin

from .models import StatusChangeLog


@admin.register(StatusChangeLog)
class StatusChangeLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity_type",
        "entity_id",
        "from_status",
        "to_status",
        "admin_user",
        "changed_at",
    )

    list_filter = (
        "entity_type",
        "from_status",
        "to_status",
        "changed_at",
    )

    search_fields = (
        "entity_type",
        "entity_id",
        "from_status",
        "to_status",
        "admin_user__email",
        "admin_user__name",
    )

    ordering = ("-changed_at", "-id")
    date_hierarchy = "changed_at"
    list_per_page = 50

    readonly_fields = (
        "entity_type",
        "entity_id",
        "from_status",
        "to_status",
        "admin_user",
        "changed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
