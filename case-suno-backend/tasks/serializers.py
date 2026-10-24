"""
Solution for: tasks/serializers.py
Build Plan Reference: Section 9 (Page 16)

Provides DRF serializers for creating, updating, and viewing follow-up tasks on matters.
"""

from rest_framework import serializers
from .models import MatterTask


class MatterTaskSerializer(serializers.ModelSerializer):
    matterId = serializers.IntegerField(source="matter_id", read_only=True)
    dueDate = serializers.DateField(source="due_date", required=False, allow_null=True)

    class Meta:
        model = MatterTask
        fields = [
            "id",
            "matterId",
            "title",
            "status",
            "dueDate",
        ]


class MatterTaskCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    dueDate = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_title(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Title cannot be empty.")
        return val


class MatterTaskUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=MatterTask.Status.choices, required=False)
    dueDate = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field ('status' or 'dueDate') must be provided.")
        return attrs
