"""
Solution for: documents/serializers.py
Build Plan Reference: Section 6, 8 & 9 (Pages 8, 16)

Provides DRF serializers for document uploads and download URL responses.
"""

from rest_framework import serializers
from .models import MatterDocument


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)


class MatterDocumentSerializer(serializers.ModelSerializer):
    uploadedBy = serializers.CharField(source="uploaded_by", read_only=True)
    uploadedAt = serializers.DateTimeField(source="uploaded_at", read_only=True)
    fileKey = serializers.CharField(source="file_key", read_only=True)

    class Meta:
        model = MatterDocument
        fields = [
            "id",
            "fileKey",
            "uploadedBy",
            "uploadedAt",
        ]


class PresignedDownloadURLResponseSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()
    matter_id = serializers.IntegerField()
    download_url = serializers.URLField()
    expires_in_seconds = serializers.IntegerField(default=300)
