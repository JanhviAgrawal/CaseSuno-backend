
from django.contrib import admin
from .models import Matter


@admin.register(Matter)
class MatterAdmin(admin.ModelAdmin):
    list_display = ("id", "proposal", "status", "opened_at", "closed_at")
    search_fields = (
        "proposal__service_name",
        "proposal__requirement__reference_id",
    )
    list_filter = ("status",)
    readonly_fields = ("opened_at",)
    filter_horizontal = ("professionals",)
