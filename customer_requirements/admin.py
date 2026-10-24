from django.contrib import admin

from .models import Requirement, RequirementEvent, RequirementMessage, RequirementNote


class RequirementMessageInline(admin.TabularInline):
    model = RequirementMessage
    extra = 0
    fields = ("sender", "body", "read_by_admin", "created_at")
    readonly_fields = ("created_at",)


class RequirementNoteInline(admin.TabularInline):
    model = RequirementNote
    extra = 0
    fields = ("body", "author", "created_at")
    readonly_fields = ("created_at",)


class RequirementEventInline(admin.TabularInline):
    model = RequirementEvent
    extra = 0
    fields = ("type", "detail", "created_at")
    readonly_fields = ("type", "detail", "created_at")
    can_delete = False


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = (
        "reference_id",
        "name",
        "mobile",
        "requirement_type",
        "city",
        "urgency",
        "status",
        "created_at",
    )
    search_fields = ("reference_id", "name", "mobile", "email", "requirement_type")
    list_filter = ("status", "urgency", "handling", "language", "city")
    readonly_fields = ("access_token", "created_at", "updated_at")
    raw_id_fields = ("assigned_professional", "reviewed_by")
    inlines = [RequirementMessageInline, RequirementNoteInline, RequirementEventInline]


@admin.register(RequirementMessage)
class RequirementMessageAdmin(admin.ModelAdmin):
    list_display = ("requirement", "sender", "read_by_admin", "created_at")
    list_filter = ("sender", "read_by_admin")
    search_fields = ("requirement__reference_id", "body")
