
import secrets
import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import AdminUser, AdminLoginOTP, AdminSession
from .serializers import (
    AdminOTPRequestSerializer,
    AdminOTPVerifySerializer,
)

from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)


class AdminOTPRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = AdminOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()

        admin = AdminUser.objects.filter(
            email__iexact=email,
            is_active=True,
        ).first()

        response_data = {
            "message": (
                "If this email belongs to an active admin, "
                "an OTP will be sent."
            )
        }

        if admin is None:
            return Response(response_data, status=status.HTTP_200_OK)

        otp = f"{secrets.randbelow(1_000_000):06d}"
        now = timezone.now()

        # Invalidate previous unused OTPs.
        AdminLoginOTP.objects.filter(
            admin_user=admin,
            used_at__isnull=True,
        ).update(used_at=now)

        AdminLoginOTP.objects.create(
            admin_user=admin,
            otp_hash=make_password(otp),
            expires_at=now + timedelta(minutes=10),
        )

        send_mail(
            subject="Your CASE SUNO admin login OTP",
            message=(
                f"Your CASE SUNO login OTP is: {otp}\n\n"
                "It expires in 10 minutes. Do not share this code."
            ),
            from_email=None,
            recipient_list=[admin.email],
            fail_silently=False,
        )

        return Response(response_data, status=status.HTTP_200_OK)


class AdminOTPVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = AdminOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        otp = serializer.validated_data["otp"]
        now = timezone.now()

        admin = AdminUser.objects.filter(
            email__iexact=email,
            is_active=True,
        ).first()

        if admin is None:
            return Response(
                {"error": "invalid_or_expired_otp"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            otp_record = (
                AdminLoginOTP.objects.select_for_update()
                .filter(
                    admin_user=admin,
                    used_at__isnull=True,
                )
                .order_by("-created_at")
                .first()
            )

            if (
                otp_record is None
                or otp_record.expires_at <= now
                or otp_record.attempts >= 5
            ):
                return Response(
                    {"error": "invalid_or_expired_otp"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not check_password(otp, otp_record.otp_hash):
                otp_record.attempts += 1

                if otp_record.attempts >= 5:
                    otp_record.used_at = now
                    otp_record.save(
                        update_fields=["attempts", "used_at"]
                    )
                else:
                    otp_record.save(update_fields=["attempts"])

                return Response(
                    {"error": "invalid_or_expired_otp"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # A valid OTP can only be used once.
            otp_record.used_at = now
            otp_record.save(update_fields=["used_at"])

            # Generate a session token; store only its hash.
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()

            AdminSession.objects.create(
                admin_user=admin,
                token_hash=token_hash,
                expires_at=now + timedelta(hours=12),
            )

        response = Response(
            {"message": "Login successful"},
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            key="case_suno_admin_session",
            value=raw_token,
            max_age=12 * 60 * 60,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Strict",
            path="/",
        )

        return response


class AdminMeView(APIView):
    authentication_classes = [AdminSessionAuthentication]

    # Do not use DRF's IsAuthenticated here:
    # our custom authentication returns an AdminUser instance.
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "name": request.user.name,
                "email": request.user.email,
                "role": request.user.role,
            },
            status=status.HTTP_200_OK,
        )


class AdminLogoutView(APIView):
    """
    Revoke active admin session and clear authentication cookie.
    POST /api/accounts/admin/logout/
    Build Plan Reference: Section 11 (Page 17) - "sessions expire and are revocable"
    """
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def post(self, request):
        if isinstance(request.auth, AdminSession):
            request.auth.revoked_at = timezone.now()
            request.auth.save(update_fields=["revoked_at"])

        response = Response(
            {"message": "Logged out successfully"},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie(
            key="case_suno_admin_session",
            path="/",
            samesite="Strict",
        )
        return response

