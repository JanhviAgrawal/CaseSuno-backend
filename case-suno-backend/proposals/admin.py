
from django.contrib import admin
from .models import ServiceProposal


@admin.register(ServiceProposal)
class ServiceProposalAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "public_id",
        "requirement",
        "service_name",
        "fee",
        "currency",
        "valid_until",
        "created_at",
    )
    search_fields = (
        "service_name",
        "requirement__reference_id",
        "requirement__name",
    )
    list_filter = ("currency", "valid_until")
    readonly_fields = ("public_id", "created_at")
