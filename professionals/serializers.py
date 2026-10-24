from rest_framework import serializers
from .models import Professional


class ProfessionalSerializer(serializers.ModelSerializer):
    isActive = serializers.BooleanField(source="is_active", default=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Professional
        fields = [
            "id",
            "name",
            "specialism",
            "contact",
            "isActive",
            "createdAt",
        ]


class ProfessionalCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=120)
    specialism = serializers.CharField(max_length=150)
    contact = serializers.CharField(max_length=255)
    isActive = serializers.BooleanField(source="is_active", required=False, default=True)

    class Meta:
        model = Professional
        fields = [
            "id",
            "name",
            "specialism",
            "contact",
            "isActive",
        ]

    def validate_name(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Name cannot be empty.")
        return val

    def validate_specialism(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Specialism cannot be empty.")
        return val

    def validate_contact(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Contact cannot be empty.")
        return val
