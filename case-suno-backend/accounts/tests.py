"""
Build Plan Section 7 (Pages 11-12)
Admin Passwordless Email OTP Login & Session Tests
"""

from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from accounts.models import AdminUser, AdminLoginOTP, AdminSession


class AdminAuthAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.admin = AdminUser.objects.create(
            name="Platform Super Admin",
            email="superadmin@casesuno.com",
            role=AdminUser.Role.SUPER_ADMIN,
            is_active=True,
        )

        self.otp_request_url = reverse("admin-login-otp")
        self.otp_verify_url = reverse("admin-login")
        self.me_url = reverse("admin-me")

    def test_request_otp_for_active_admin_sends_email_and_stores_hash(self):
        response = self.client.post(
            self.otp_request_url,
            {"email": "superadmin@casesuno.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Confirm OTP was generated in DB
        otp_record = AdminLoginOTP.objects.filter(admin_user=self.admin).first()
        self.assertIsNotNone(otp_record)
        self.assertTrue(otp_record.expires_at > timezone.now())

        # Confirm email was dispatched via console/test outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("admin login OTP", mail.outbox[0].subject)

    def test_request_otp_for_unknown_email_returns_generic_message(self):
        response = self.client.post(
            self.otp_request_url,
            {"email": "unknown@casesuno.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should not create any DB OTP or send email
        self.assertEqual(AdminLoginOTP.objects.filter(admin_user__email="unknown@casesuno.com").count(), 0)

    def test_verify_otp_creates_session_and_sets_cookie(self):
        from django.contrib.auth.hashers import make_password

        # Create known OTP
        plain_otp = "654321"
        AdminLoginOTP.objects.create(
            admin_user=self.admin,
            otp_hash=make_password(plain_otp),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(
            self.otp_verify_url,
            {"email": "superadmin@casesuno.com", "otp": plain_otp},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("case_suno_admin_session", response.cookies)
        cookie = response.cookies["case_suno_admin_session"]
        self.assertTrue(cookie["httponly"])

        # Authenticated AdminMeView check using cookie
        self.client.cookies["case_suno_admin_session"] = cookie.value
        me_res = self.client.get(self.me_url)
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.data["email"], "superadmin@casesuno.com")
        self.assertEqual(me_res.data["name"], "Platform Super Admin")

    def test_verify_invalid_otp_is_rejected(self):
        from django.contrib.auth.hashers import make_password

        AdminLoginOTP.objects.create(
            admin_user=self.admin,
            otp_hash=make_password("111111"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(
            self.otp_verify_url,
            {"email": "superadmin@casesuno.com", "otp": "999999"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
