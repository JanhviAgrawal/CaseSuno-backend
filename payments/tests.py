import hashlib
import hmac
import json
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from customer_requirements.models import Requirement
from proposals.models import ServiceProposal
from payments.models import Payment
from matters.models import Matter


@override_settings(RAZORPAY_WEBHOOK_SECRET="test_webhook_secret_key_123")
class PaymentWebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.webhook_url = reverse("razorpay-webhook")
        self.webhook_secret = "test_webhook_secret_key_123"

        # Setup test requirement & proposal
        self.requirement = Requirement.objects.create(
            reference_id="CS-2026-00001",
            name="Amit Patel",
            mobile="9876543210",
            email="amit@example.com",
            city="Delhi",
            requirement_type="Legal Notice",
            description="Drafting and sending a legal notice.",
            status="payment_pending",
            consent_given=True,
        )

        self.proposal = ServiceProposal.objects.create(
            requirement=self.requirement,
            service_name="Legal Notice Drafting",
            scope="Comprehensive notice drafting and dispatch",
            fee=Decimal("5000.00"),
            currency="INR",
            valid_until=timezone.localdate() + timedelta(days=7),
        )

        self.order_id = "order_test_123456789"
        self.payment = Payment.objects.create(
            proposal=self.proposal,
            gateway_order_id=self.order_id,
            amount=self.proposal.fee,
            status=Payment.Status.PENDING,
        )

    def _generate_payload_and_signature(self):
        payload_dict = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_987654321",
                        "order_id": self.order_id,
                        "amount": 500000,  # 5000 INR in paise
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        body_bytes = json.dumps(payload_dict).encode("utf-8")
        signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return body_bytes, signature

    def test_webhook_creates_matter_and_is_idempotent(self):
        body_bytes, signature = self._generate_payload_and_signature()

        # First webhook post
        response1 = self.client.post(
            self.webhook_url,
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(Matter.objects.filter(proposal=self.proposal).count(), 1)

        # Refresh database state
        self.payment.refresh_from_db()
        self.requirement.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.assertEqual(self.requirement.status, "converted")

        # Second webhook post with identical payload and signature (idempotency test)
        response2 = self.client.post(
            self.webhook_url,
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # Confirm exactly 1 Matter remains, no duplicates created
        self.assertEqual(Matter.objects.filter(proposal=self.proposal).count(), 1)
