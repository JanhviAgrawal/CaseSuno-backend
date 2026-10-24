
from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "proposal", "gateway_order_id",
        "gateway_payment_id", "amount", "status",
        "paid_at", "created_at",
    )
    search_fields = (
        "gateway_order_id", "gateway_payment_id",
        "proposal__service_name",
        "proposal__requirement__reference_id",
    )
    list_filter = ("status",)
    readonly_fields = ("created_at",)
