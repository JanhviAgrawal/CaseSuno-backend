"""
Solution for: customer_requirements/serializers.py
Build Plan Reference: Section 7 & 11 (Pages 11, 17)

Changes Made:
1. Implemented get_documentUrls() in AdminRequirementDetailSerializer.
   Instead of returning hardcoded [], it now uses create_presigned_download_url
   from documents.services.storage to generate 5-minute signed S3 URLs for each key
   in obj.documents. If storage is unconfigured or a key fails, it gracefully handles it.
2. All original validation logic, aliases (camelCase <-> snake_case), and models preserved.
"""

from rest_framework import serializers
from .models import Requirement
from documents.services.storage import create_presigned_download_url, DocumentServiceUnavailable


class RequirementCreateSerializer(serializers.ModelSerializer):
    requirementType = serializers.CharField(
        source="requirement_type",
        max_length=100,
    )
    otherParty = serializers.CharField(
        source="other_party",
        required=False,
        allow_blank=True,
    )
    consentGiven = serializers.BooleanField(
        source="consent_given",
    )
    documents = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        max_length=10,
    )

    class Meta:
        model = Requirement
        fields = [
            "name",
            "mobile",
            "email",
            "city",
            "requirementType",
            "description",
            "otherParty",
            "documents",
            "urgency",
            "consentGiven",
        ]
        extra_kwargs = {
            "email": {"required": True, "allow_blank": False},
            "city": {"required": True, "allow_blank": False},
        }

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "Name must contain at least 2 characters."
            )
        return value

    def validate_mobile(self, value):
        value = value.strip()
        if (
            len(value) != 10
            or not value.isdigit()
            or value[0] not in "6789"
        ):
            raise serializers.ValidationError(
                "Enter a valid 10-digit Indian mobile number."
            )
        return value

    def validate_description(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError(
                "Description must contain at least 10 characters."
            )
        if len(value) > 5000:
            raise serializers.ValidationError(
                "Description cannot exceed 5000 characters."
            )
        return value

    def validate_consentGiven(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Consent is required to submit a requirement."
            )
        return value


class RequirementPublicSerializer(serializers.ModelSerializer):
    referenceId = serializers.CharField(
        source="reference_id",
        read_only=True,
    )
    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
    )
    whatsappChat = serializers.SerializerMethodField()
    proposal = serializers.SerializerMethodField()
    matter = serializers.SerializerMethodField()

    class Meta:
        model = Requirement
        fields = [
            "referenceId",
            "status",
            "createdAt",
            "whatsappChat",
            "proposal",
            "matter",
        ]

    def get_whatsappChat(self, obj):
        from common.services.notifications import generate_whatsapp_chat_metadata
        return generate_whatsapp_chat_metadata(
            reference_id=obj.reference_id,
            customer_name=obj.name,
        )

    def get_proposal(self, obj):
        proposal = getattr(obj, "proposal", None)
        if proposal and obj.status in ("service_proposed", "payment_pending", "converted"):
            return {
                "proposalId": str(proposal.public_id),
                "serviceName": proposal.service_name,
                "fee": str(proposal.fee),
                "currency": proposal.currency,
                "validUntil": proposal.valid_until,
            }
        return None

    def get_matter(self, obj):
        proposal = getattr(obj, "proposal", None)
        if not proposal:
            return None
        matter = getattr(proposal, "matter", None)
        if not matter:
            return None

        return {
            "matterId": matter.pk,
            "status": matter.status,
            "openedAt": matter.opened_at,
            "closedAt": matter.closed_at,
            "professionals": [
                {
                    "name": p.name,
                    "specialism": p.specialism,
                }
                for p in matter.professionals.filter(is_active=True)
            ],
            "milestones": [
                {
                    "title": t.title,
                    "status": t.status,
                    "dueDate": t.due_date,
                }
                for t in matter.tasks.all()
            ],
        }



class AdminRequirementListSerializer(serializers.ModelSerializer):
    referenceId = serializers.CharField(
        source="reference_id",
        read_only=True,
    )
    requirementType = serializers.CharField(
        source="requirement_type",
        read_only=True,
    )
    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
    )

    class Meta:
        model = Requirement
        fields = [
            "id",
            "referenceId",
            "name",
            "email",
            "city",
            "requirementType",
            "urgency",
            "status",
            "createdAt",
        ]


class AdminRequirementDetailSerializer(serializers.ModelSerializer):
    referenceId = serializers.CharField(
        source="reference_id",
        read_only=True,
    )
    requirementType = serializers.CharField(
        source="requirement_type",
        read_only=True,
    )
    otherParty = serializers.CharField(
        source="other_party",
        read_only=True,
        allow_blank=True,
    )
    consentGiven = serializers.BooleanField(
        source="consent_given",
        read_only=True,
    )
    internalNotes = serializers.CharField(
        source="internal_notes",
        read_only=True,
    )
    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
    )
    documentUrls = serializers.SerializerMethodField()

    class Meta:
        model = Requirement
        fields = [
            "id",
            "referenceId",
            "name",
            "mobile",
            "email",
            "city",
            "requirementType",
            "description",
            "otherParty",
            "urgency",
            "consentGiven",
            "status",
            "internalNotes",
            "documentUrls",
            "createdAt",
        ]

    def get_documentUrls(self, obj):
        """
        Generate short-lived (5-minute) presigned download URLs for S3 object keys.
        Never returns raw S3 bucket keys to the client.
        Matches PDF Section 7 & 11 (Pages 11, 17).
        """
        keys = obj.documents if isinstance(obj.documents, list) else []
        signed_urls = []
        for key in keys:
            if not isinstance(key, str) or not key.strip():
                continue
            try:
                url = create_presigned_download_url(key.strip(), expires_in=300)
                signed_urls.append(url)
            except DocumentServiceUnavailable:
                # If S3 service is offline/unconfigured during development, return null placeholder
                signed_urls.append(None)
        return signed_urls


class RequirementStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=Requirement.Status.choices
    )
