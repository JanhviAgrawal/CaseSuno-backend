
from django.contrib import admin
from .models import MatterDocument


@admin.register(MatterDocument)
class MatterDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "matter", "file_key", "uploaded_by", "uploaded_at")
    search_fields = ("file_key", "uploaded_by")
    list_filter = ("uploaded_at",)
    readonly_fields = ("uploaded_at",)
