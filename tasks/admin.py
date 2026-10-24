
from django.contrib import admin
from .models import MatterTask


@admin.register(MatterTask)
class MatterTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "matter", "status", "due_date")
    search_fields = ("title",)
    list_filter = ("status", "due_date")
