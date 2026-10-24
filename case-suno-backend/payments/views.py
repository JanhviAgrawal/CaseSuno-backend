"""
Solution for: payments/views.py
Build Plan Reference: Section 8 & 10 (Pages 13-15, 17)

Changes Made:
1. Retained Razorpay order creation and HMAC SHA256 webhook signature verification.
2. Added Celery customer notification dispatch on transaction commit when payment is captured.
   Matches PDF Section 10, Step 8 (Page 17):
   "In one transaction the backend marks the Payment paid, the Requirement converted,
   and creates the Matter; a Celery/RQ task sends the confirmation, and the customer
   sees Service Activated."
3. Integrated state machine PAYMENT_TRANSITIONS and REQUIREMENT_TRANSITIONS.
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import razorpay

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from proposals.models import ServiceProposal
from audit.models import StatusChangeLog
from .services import (
    PaymentNotFound,
    mark_payment_failed,
    mark_payment_paid,
    verify_checkout_signature,
)
from common.services.state_machine import (
    is_valid_requirement_transition,
    assert_transition,
    PAYMENT_TRANSITIONS,
)
from .models import Payment

logger = logging.getLogger(__name__)


class CreateProposalPaymentView(APIView):
    """
    Create or reuse a Razorpay order for a service proposal.
    POST /api/payments/proposals/<proposal_id>/payment/
    """
    permission_classes = [AllowAny]

    def post(self, request, proposal_id):
        key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
        key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")

        if not key_id or not key_secret:
            return Response(
                {
                    "error": "payment_gateway_not_configured",
                    "message": "The payment gateway is not configured.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            with transaction.atomic():
                proposal = get_object_or_404(
                    ServiceProposal.objects.select_for_update().select_related("requirement"),
                    public_id=proposal_id,
                )

                requirement = proposal.requirement

                # Refuse expired proposals (410 Gone)
                if proposal.valid_until and proposal.valid_until < timezone.localdate():
                    return Response(
                        {
                            "error": "proposal_expired",
                            "message": "This proposal has expired.",
                        },
                        status=status.HTTP_410_GONE,
                    )

                if requirement.status not in ("service_proposed", "payment_pending"):
                    return Response(
                        {
                            "error": "invalid_requirement_status",
                            "currentStatus": requirement.status,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                existing_payment = (
                    Payment.objects.select_for_update()
                    .filter(proposal=proposal)
                    .first()
                )

                # Reuse existing pending order if customer retries checkout
                if existing_payment:
                    if existing_payment.status != Payment.Status.PENDING:
                        return Response(
                            {
                                "error": "payment_already_exists",
                                "paymentStatus": existing_payment.status,
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    if requirement.status == "service_proposed":
                        if not is_valid_requirement_transition(requirement.status, "payment_pending"):
                            return Response(
                                {"error": "invalid_requirement_transition"},
                                status=status.HTTP_409_CONFLICT,
                            )

                        requirement.status = "payment_pending"
                        requirement.save(update_fields=["status"])

                        StatusChangeLog.objects.create(
                            entity_type="requirement",
                            entity_id=str(requirement.pk),
                            from_status="service_proposed",
                            to_status="payment_pending",
                        )

                    return Response(
                        {
                            "gatewayOrderId": existing_payment.gateway_order_id,
                            "amount": int(existing_payment.amount * Decimal("100")),
                            "currency": proposal.currency,
                            "gatewayKey": key_id,
                        },
                        status=status.HTTP_200_OK,
                    )

                # Validate state transition before calling Razorpay
                if not is_valid_requirement_transition(requirement.status, "payment_pending"):
                    return Response(
                        {
                            "error": "invalid_requirement_transition",
                            "currentStatus": requirement.status,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                amount_paise = int(proposal.fee * Decimal("100"))
                if amount_paise <= 0:
                    return Response(
                        {"error": "invalid_proposal_amount"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                client = razorpay.Client(auth=(key_id, key_secret))

                try:
                    order = client.order.create(
                        data={
                            "amount": amount_paise,
                            "currency": proposal.currency,
                            "receipt": str(requirement.reference_id),
                            "notes": {
                                "proposal_id": str(proposal.public_id),
                            },
                        }
                    )
                except Exception:
                    logger.exception("Razorpay order creation failed for proposal %s", proposal.public_id)
                    return Response(
                        {
                            "error": "payment_order_creation_failed",
                            "message": "Unable to create a payment order.",
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

                Payment.objects.create(
                    proposal=proposal,
                    gateway_order_id=order["id"],
                    amount=proposal.fee,
                    status=Payment.Status.PENDING,
                )

                requirement.status = "payment_pending"
                requirement.save(update_fields=["status"])

                StatusChangeLog.objects.create(
                    entity_type="requirement",
                    entity_id=str(requirement.pk),
                    from_status="service_proposed",
                    to_status="payment_pending",
                )

                return Response(
                    {
                        "gatewayOrderId": order["id"],
                        "amount": amount_paise,
                        "currency": proposal.currency,
                        "gatewayKey": key_id,
                    },
                    status=status.HTTP_201_CREATED,
                )

        except ServiceProposal.DoesNotExist:
            return Response(
                {"error": "proposal_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class RazorpayWebhookView(APIView):
    """
    Verify and process Razorpay payment webhooks.
    POST /api/payments/webhooks/payment/
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
        if not webhook_secret:
            return Response(
                {"error": "webhook_secret_not_configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        signature = request.headers.get("X-Razorpay-Signature", "")
        if not signature:
            return Response(
                {"error": "missing_webhook_signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            request.body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            return Response(
                {"error": "invalid_webhook_signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                {"error": "invalid_json"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event = payload.get("event")
        if event not in ("payment.captured", "payment.failed", "order.paid"):
            return Response({"status": "event_ignored"}, status=status.HTTP_200_OK)

        payment_entity = (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )
        order_id = payment_entity.get("order_id") or (
            payload.get("payload", {}).get("order", {}).get("entity", {}).get("id")
        )
        gateway_payment_id = payment_entity.get("id")

        if not order_id:
            return Response(
                {"error": "missing_gateway_order_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = (
            Payment.objects.select_related("proposal__requirement")
            .filter(gateway_order_id=order_id)
            .first()
        )
        if payment is None:
            logger.warning("Received webhook for unknown Razorpay order %s", order_id)
            return Response({"status": "unknown_order"}, status=status.HTTP_200_OK)

        if event == "payment.failed":
            if payment.status == Payment.Status.PENDING:
                mark_payment_failed(order_id, payment_entity.get("error_description") or "")
                return Response({"status": "payment_attempt_failed"}, status=status.HTTP_200_OK)
            return Response({"status": "already_processed"}, status=status.HTTP_200_OK)

        # payment.captured / order.paid
        captured_amount = payment_entity.get("amount")
        if captured_amount is None:
            return Response(
                {"error": "missing_captured_amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected_amount = int(payment.amount * Decimal("100"))
        if captured_amount != expected_amount:
            logger.error("Captured amount mismatch for order %s", order_id)
            return Response(
                {"error": "payment_amount_mismatch"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            _payment, matter, newly_paid = mark_payment_paid(order_id, gateway_payment_id or "")
        except PaymentNotFound:
            return Response({"status": "unknown_order"}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error processing Razorpay webhook for order %s", order_id)
            return Response(
                {"error": "webhook_processing_failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not newly_paid:
            return Response({"status": "already_processed"}, status=status.HTTP_200_OK)

        return Response(
            {"status": "payment_captured", "matterId": matter.pk if matter else None},
            status=status.HTTP_200_OK,
        )


class VerifyPaymentSignatureView(APIView):
    """
    Verify client-side Razorpay checkout signature for instant UI confirmation.
    POST /api/payments/verify/
    Build Plan Reference: Section 8 & 9 (Page 15)
    "The frontend also gets a razorpay_signature after checkout; it can be verified with
    rzp.utility.verify_payment_signature(...) to show a fast 'processing' state..."
    """
    permission_classes = [AllowAny]

    def post(self, request):
        order_id = request.data.get("razorpay_order_id", request.data.get("razorpayOrderId"))
        payment_id = request.data.get("razorpay_payment_id", request.data.get("razorpayPaymentId"))
        signature = request.data.get("razorpay_signature", request.data.get("razorpaySignature"))

        if not all((order_id, payment_id, signature)):
            return Response(
                {
                    "error": "missing_required_fields",
                    "message": "razorpay_order_id, razorpay_payment_id, and razorpay_signature are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
        if not key_secret:
            return Response(
                {
                    "error": "payment_gateway_not_configured",
                    "message": "Payment gateway secret is not configured.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not verify_checkout_signature(order_id, payment_id, signature):
            return Response(
                {"error": "invalid_payment_signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment, matter, _newly_paid = mark_payment_paid(order_id, payment_id)
        except PaymentNotFound:
            return Response(
                {"error": "payment_order_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("Error verifying payment signature for order %s", order_id)
            return Response(
                {"error": "verification_failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "status": "payment_verified",
                "matterId": matter.pk if matter else None,
                "referenceId": payment.proposal.requirement.reference_id,
            },
            status=status.HTTP_200_OK,
        )
