from rest_framework import serializers
from .models import Payment


class PaymentOrderResponseSerializer(serializers.Serializer):
    """
    Response returned by POST /api/payments/proposals/<uuid>/payment/
    Supplies the frontend with what it needs to initialize Razorpay checkout.
    """
    gatewayOrderId = serializers.CharField()
    amount = serializers.IntegerField(help_text="Amount in paise (smallest currency unit)")
    currency = serializers.CharField(max_length=3)
    gatewayKey = serializers.CharField()


class PaymentDetailSerializer(serializers.ModelSerializer):
    proposalId = serializers.UUIDField(source="proposal.public_id", read_only=True)
    gatewayOrderId = serializers.CharField(source="gateway_order_id", read_only=True)
    gatewayPaymentId = serializers.CharField(source="gateway_payment_id", read_only=True)
    paidAt = serializers.DateTimeField(source="paid_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "proposalId",
            "gatewayOrderId",
            "gatewayPaymentId",
            "amount",
            "status",
            "paidAt",
            "createdAt",
        ]
