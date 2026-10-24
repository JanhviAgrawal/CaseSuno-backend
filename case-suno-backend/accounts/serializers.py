
from rest_framework import serializers


class AdminOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

class AdminOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(regex=r"^\d{6}$")