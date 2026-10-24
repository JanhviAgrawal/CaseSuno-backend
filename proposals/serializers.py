from rest_framework import serializers
from django.utils import timezone
from .models import ServiceProposal


class ServiceProposalCreateSerializer(serializers.ModelSerializer):
    serviceName = serializers.CharField(
        source="service_name",
        max_length=200,
    )
    validUntil = serializers.DateField(
        source="valid_until",
    )

    class Meta:
        model = ServiceProposal
        fields = [
            "serviceName",
            "scope",
            "fee",
            "currency",
            "validUntil",
        ]

    def validate_fee(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Fee must be greater than zero."
            )
        return value
    
class ServiceProposalPublicSerializer(serializers.ModelSerializer):
    proposalId = serializers.UUIDField(
        source="public_id",
        read_only=True,
    )
    serviceName = serializers.CharField(
        source="service_name",
        read_only=True,
    )
    validUntil = serializers.DateField(
        source="valid_until",
        read_only=True,
    )
    requirementReferenceId = serializers.CharField(
        source="requirement.reference_id",
        read_only=True,
    )
    expired = serializers.SerializerMethodField()

    class Meta:
        model = ServiceProposal
        fields = [
            "proposalId",
            "requirementReferenceId",
            "serviceName",
            "scope",
            "fee",
            "currency",
            "validUntil",
            "expired",
        ]

    def get_expired(self, obj):
        return obj.valid_until < timezone.localdate()
