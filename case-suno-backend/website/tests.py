"""
End-to-end tests for the casesuno.in website API (/api/web/).

Covers the full journey the website performs:
  customer submits enquiry -> tracks it -> admin logs in, replies, assigns a lawyer,
  requests a platform fee -> customer pays via Razorpay -> admin sees revenue.
"""

import hashlib
import hmac
import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from accounts.models import AdminUser
from customer_requirements.models import Requirement, RequirementMessage
from matters.models import Matter
from payments.models import Payment
from professionals.models import Professional

WEB_KEY = "test-website-key"


@override_settings(
    WEBSITE_API_KEY=WEB_KEY,
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="rzp_test_secret",
    RAZORPAY_WEBHOOK_SECRET="rzp_webhook_secret",
    ADMIN_NOTIFY_EMAILS=["ops@casesuno.in"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class WebsiteFlowTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(HTTP_X_WEBSITE_KEY=WEB_KEY, HTTP_X_CLIENT_IP="203.0.113.7")

        User = get_user_model()
        user = User.objects.create_user(username="admin@casesuno.in", email="admin@casesuno.in", password="Str0ng-pass!")
        self.admin = AdminUser.objects.create(user=user, name="Ops", email="admin@casesuno.in", role="super_admin")

        self.enquiry_payload = {
            "category": "Property & Land",
            "description": "My neighbour has encroached on my plot.",
            "fullName": "Ravi Patel",
            "phone": "+91 94271 62414",
            "email": "ravi@example.com",
            "city": "Surat",
            "language": "gu",
        }

    # -- helpers -------------------------------------------------------------
    def login(self):
        res = self.client.post(reverse("web-admin-login"), {"email": "ADMIN@casesuno.in", "password": "Str0ng-pass!"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["ok"])
        return APIClient(
            HTTP_X_WEBSITE_KEY=WEB_KEY,
            HTTP_AUTHORIZATION=f"AdminSession {res.data['token']}",
        )

    def submit(self, **overrides):
        payload = {**self.enquiry_payload, **overrides}
        return self.client.post(reverse("web-enquiry-create"), payload, format="json")

    # -- tests ---------------------------------------------------------------
    def test_requires_website_key(self):
        res = APIClient().post(reverse("web-enquiry-create"), self.enquiry_payload, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data, {"ok": False, "error": "Forbidden"})

    def test_enquiry_validation_and_honeypot(self):
        self.assertEqual(self.submit(description="hey").status_code, 400)
        res = self.submit(phone="12345678")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"], "Please enter a valid mobile number.")

        res = self.submit(website="http://spam.example")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["reference"], "CS-RECEIVED")
        self.assertEqual(Requirement.objects.count(), 0)

    def test_enquiry_rate_limit_is_per_visitor(self):
        for _ in range(6):
            self.assertEqual(self.submit().status_code, 201)
        res = self.submit()
        self.assertEqual(res.status_code, 429)
        self.assertFalse(res.data["ok"])
        other = APIClient(HTTP_X_WEBSITE_KEY=WEB_KEY, HTTP_X_CLIENT_IP="198.51.100.1")
        self.assertEqual(other.post(reverse("web-enquiry-create"), self.enquiry_payload, format="json").status_code, 201)

    def test_full_customer_and_admin_journey(self):
        # 1. Customer submits an enquiry (email/city optional, +91 phone accepted)
        with self.captureOnCommitCallbacks(execute=True):
            res = self.submit()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertRegex(res.data["reference"], r"^CS-\d{4}-\d{5}$")
        token = res.data["token"]
        reference = res.data["reference"]
        # confirmation to customer + alert to ops
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["ops@casesuno.in", "ravi@example.com"])

        # 2. Lookup by reference + phone (any format, last 10 digits)
        res = self.client.post(reverse("web-track-lookup"), {"reference": reference.lower(), "phone": "9427162414"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["token"], token)
        res = self.client.post(reverse("web-track-lookup"), {"reference": reference, "phone": "9999999999"}, format="json")
        self.assertEqual(res.status_code, 404)

        # 3. Tracking page data
        res = self.client.get(reverse("web-track-detail", args=[token]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "NEW")
        self.assertTrue(res.data["paymentEnabled"])
        self.assertIsNone(res.data["lawyer"])

        # 4. Customer sends a message
        res = self.client.post(reverse("web-track-message", args=[token]), {"body": "Any update?"}, format="json")
        self.assertEqual(res.status_code, 201)

        # 5. Admin login + me (unread count)
        admin = self.login()
        res = admin.get(reverse("web-admin-me"))
        self.assertEqual(res.data["email"], "admin@casesuno.in")
        self.assertEqual(res.data["unread"], 1)

        # 6. List + search + status filter
        res = admin.get(reverse("web-admin-enquiries"), {"q": "ravi"})
        self.assertEqual(res.data["count"], 1)
        item = res.data["items"][0]
        self.assertEqual(item["unread"], 1)
        self.assertEqual(item["priority"], "NORMAL")
        pk = item["id"]
        self.assertEqual(admin.get(reverse("web-admin-enquiries"), {"status": "PAID"}).data["count"], 0)
        self.assertEqual(res.data["statusCounts"]["NEW"], 1)

        # 7. Detail marks messages read
        res = admin.get(reverse("web-admin-enquiry", args=[pk]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["enquiry"]["reference"], reference)
        self.assertEqual(res.data["enquiry"]["accessToken"], token)
        self.assertEqual(admin.get(reverse("web-admin-me")).data["unread"], 0)

        # 8. Admin reply moves NEW -> IN_REVIEW
        res = admin.post(reverse("web-admin-enquiry-messages", args=[pk]), {"body": "We are reviewing."}, format="json")
        self.assertEqual(res.status_code, 201)
        detail = admin.get(reverse("web-admin-enquiry", args=[pk])).data["enquiry"]
        self.assertEqual(detail["status"], "IN_REVIEW")
        self.assertIn("STATUS_CHANGED", [e["type"] for e in detail["events"]])

        # 9. Lawyers: create, assign, share
        res = admin.post(reverse("web-admin-lawyers"), {"name": "Adv. Mehta", "phone": "9825000000", "email": "", "specialization": "Property", "city": "Surat"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        lawyer_id = res.data["id"]
        self.assertEqual(admin.post(reverse("web-admin-lawyers"), {"name": "X"}, format="json").status_code, 400)

        res = admin.patch(
            reverse("web-admin-enquiry", args=[pk]),
            {"priority": "URGENT", "handling": "LAWYER", "lawyerId": lawyer_id, "shareLawyerWithClient": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(admin.patch(reverse("web-admin-enquiry", args=[pk]), {"status": "BOGUS"}, format="json").status_code, 400)
        lawyers = admin.get(reverse("web-admin-lawyers")).data["lawyers"]
        self.assertEqual(lawyers[0]["cases"], 1)
        track = self.client.get(reverse("web-track-detail", args=[token])).data
        self.assertEqual(track["lawyer"]["name"], "Adv. Mehta")

        # 10. Internal note (not visible to customer)
        self.assertEqual(admin.post(reverse("web-admin-enquiry-notes", args=[pk]), {"body": "Call tomorrow"}, format="json").status_code, 201)

        # 11. Request platform fee
        res = admin.post(
            reverse("web-admin-enquiry-request-payment", args=[pk]),
            {"amountRupees": 499, "note": "Case review", "message": "Please pay the platform fee."},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        track = self.client.get(reverse("web-track-detail", args=[token])).data
        self.assertEqual(track["status"], "AWAITING_PAYMENT")
        self.assertEqual(track["feeAmount"], 49900)

        # 12. Customer starts checkout (Razorpay mocked)
        with mock.patch("website.views.create_razorpay_order", return_value={"id": "order_ABC123"}) as m:
            res = self.client.post(reverse("web-payment-create-order"), {"token": token}, format="json")
            self.assertEqual(res.status_code, 200, res.data)
            self.assertEqual(res.data["orderId"], "order_ABC123")
            self.assertEqual(res.data["amount"], 49900)
            self.assertEqual(res.data["keyId"], "rzp_test_key")
            # Retrying reuses the same order
            res = self.client.post(reverse("web-payment-create-order"), {"token": token}, format="json")
            self.assertEqual(res.data["orderId"], "order_ABC123")
            self.assertEqual(m.call_count, 1)

        # 13. Verify checkout signature
        bad = self.client.post(reverse("web-payment-verify"), {"razorpay_order_id": "order_ABC123", "razorpay_payment_id": "pay_1", "razorpay_signature": "nope"}, format="json")
        self.assertEqual(bad.status_code, 400)
        sig = hmac.new(b"rzp_test_secret", b"order_ABC123|pay_XYZ", hashlib.sha256).hexdigest()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(reverse("web-payment-verify"), {"razorpay_order_id": "order_ABC123", "razorpay_payment_id": "pay_XYZ", "razorpay_signature": sig}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual([m.to[0] for m in mail.outbox], ["ravi@example.com"])
        self.assertIn(f"/track/{token}", mail.outbox[0].body)

        req = Requirement.objects.get(pk=pk)
        self.assertEqual(req.status, Requirement.Status.CONVERTED)
        matter = Matter.objects.get(proposal__requirement=req)
        self.assertEqual(list(matter.professionals.values_list("pk", flat=True)), [int(lawyer_id)])

        track = self.client.get(reverse("web-track-detail", args=[token])).data
        self.assertEqual(track["status"], "PAID")
        self.assertEqual(track["paid"]["amount"], 49900)

        # 14. Webhook arriving afterwards is idempotent
        body = json.dumps({
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_XYZ", "order_id": "order_ABC123", "amount": 49900}}},
        }).encode()
        wsig = hmac.new(b"rzp_webhook_secret", body, hashlib.sha256).hexdigest()
        res = self.client.post(reverse("razorpay-webhook"), data=body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=wsig)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "already_processed")
        self.assertEqual(Matter.objects.count(), 1)

        # 15. Fee cannot be requested again once paid
        res = admin.post(reverse("web-admin-enquiry-request-payment", args=[pk]), {"amountRupees": 10, "message": "again"}, format="json")
        self.assertEqual(res.status_code, 409)

        # 16. Dashboard + payments
        dash = admin.get(reverse("web-admin-dashboard")).data
        self.assertEqual(dash["total"], 1)
        self.assertEqual(dash["revenue"], 49900)
        self.assertEqual(dash["paidCount"], 1)
        self.assertEqual(dash["requestedCount"], 1)
        self.assertEqual(dash["statusCounts"]["PAID"], 1)
        self.assertEqual(dash["categories"][0], {"category": "Property & Land", "count": 1})
        self.assertEqual(len(dash["lastDays"]), 1)

        pays = admin.get(reverse("web-admin-payments")).data
        self.assertEqual(pays["paidSum"], 49900)
        self.assertEqual(pays["payments"][0]["status"], "PAID")
        self.assertEqual(pays["payments"][0]["enquiry"]["reference"], reference)

        # 17. Moving to IN_PROGRESS / CLOSED; closed requests refuse client messages
        self.assertEqual(admin.patch(reverse("web-admin-enquiry", args=[pk]), {"status": "CLOSED"}, format="json").status_code, 200)
        res = self.client.post(reverse("web-track-message", args=[token]), {"body": "hello?"}, format="json")
        self.assertEqual(res.status_code, 409)

        # 18. Logout revokes the session
        self.assertEqual(admin.post(reverse("web-admin-logout")).status_code, 200)
        res = admin.get(reverse("web-admin-me"))
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data, {"ok": False, "error": "Unauthorized"})

    def test_fee_change_replaces_unpaid_order(self):
        token = self.submit().data["token"]
        pk = Requirement.objects.get(access_token=token).pk
        admin = self.login()
        admin.post(reverse("web-admin-enquiry-request-payment", args=[pk]), {"amountRupees": 100, "message": "Pay"}, format="json")
        with mock.patch("website.views.create_razorpay_order", side_effect=[{"id": "order_1"}, {"id": "order_2"}]):
            self.assertEqual(self.client.post(reverse("web-payment-create-order"), {"token": token}, format="json").data["orderId"], "order_1")
            admin.post(reverse("web-admin-enquiry-request-payment", args=[pk]), {"amountRupees": 250.5, "message": "Updated"}, format="json")
            res = self.client.post(reverse("web-payment-create-order"), {"token": token}, format="json")
            self.assertEqual(res.data["orderId"], "order_2")
            self.assertEqual(res.data["amount"], 25050)
        self.assertEqual(Payment.objects.count(), 1)

    def test_admin_endpoints_reject_anonymous_and_bad_login(self):
        self.assertEqual(self.client.get(reverse("web-admin-dashboard")).status_code, 401)
        res = self.client.post(reverse("web-admin-login"), {"email": "admin@casesuno.in", "password": "wrong"}, format="json")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["error"], "Invalid email or password.")

    def test_payment_not_due(self):
        token = self.submit().data["token"]
        res = self.client.post(reverse("web-payment-create-order"), {"token": token}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_legacy_status_values_display_as_website_status(self):
        token = self.submit().data["token"]
        Requirement.objects.filter(access_token=token).update(status="contacted")
        self.assertEqual(self.client.get(reverse("web-track-detail", args=[token])).data["status"], "IN_REVIEW")
        admin = self.login()
        self.assertEqual(admin.get(reverse("web-admin-enquiries"), {"status": "IN_REVIEW"}).data["count"], 1)

    def test_unread_messages_counted(self):
        token = self.submit().data["token"]
        self.client.post(reverse("web-track-message", args=[token]), {"body": "one"}, format="json")
        self.client.post(reverse("web-track-message", args=[token]), {"body": "two"}, format="json")
        self.assertEqual(RequirementMessage.objects.filter(read_by_admin=False).count(), 2)
        admin = self.login()
        self.assertEqual(admin.get(reverse("web-admin-dashboard")).data["unread"], 2)


class EnsureAdminCommandTests(APITestCase):
    def test_creates_and_updates_admin(self):
        from django.core.management import call_command

        call_command("ensure_admin", email="Owner@CaseSuno.in", password="first-pass-123", name="Owner")
        call_command("ensure_admin", email="owner@casesuno.in", password="second-pass-456", name="Owner")
        self.assertEqual(AdminUser.objects.count(), 1)
        admin = AdminUser.objects.get()
        self.assertEqual(admin.email, "owner@casesuno.in")
        self.assertTrue(admin.user.check_password("second-pass-456"))
        self.assertTrue(admin.user.is_superuser)

    def test_skips_quietly_when_not_configured(self):
        from django.core.management import call_command

        call_command("ensure_admin", email="", password="", if_configured=True)
        self.assertEqual(AdminUser.objects.count(), 0)


class ThrottleRateParsingTests(APITestCase):
    def test_parse_rates(self):
        from website.security import WebsiteRateThrottle

        t = WebsiteRateThrottle.__new__(WebsiteRateThrottle)
        self.assertEqual(t.parse_rate("6/10m"), (6, 600))
        self.assertEqual(t.parse_rate("5/minute"), (5, 60))
        self.assertEqual(t.parse_rate("8/15m"), (8, 900))
        self.assertEqual(t.parse_rate("100/day"), (100, 86400))
        self.assertTrue(re.match(r"^\d", "1"))
