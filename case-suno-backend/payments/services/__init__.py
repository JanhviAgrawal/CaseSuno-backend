"""
Payment domain services shared by:
  * the Razorpay webhook              (payments.views.RazorpayWebhookView)
  * the Build Plan verify endpoint    (payments.views.VerifyPaymentSignatureView)
  * the website checkout              (website.views)

Everything that happens when a payment succeeds lives in one place so the
behaviour is identical (and idempotent) no matter which path arrives first.
"""

import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def razorpay_configured() -> bool:
    return bool(
        getattr(settings, "RAZORPAY_KEY_ID", "")
        and getattr(settings, "RAZORPAY_KEY_SECRET", "")
    )


def to_paise(amount: Decimal) -> int:
    return int((Decimal(amount) * Decimal("100")).quantize(Decimal("1")))


def format_inr(paise: int) -> str:
    rupees = Decimal(paise) / Decimal("100")
    text = f"{rupees:,.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return f"₹{text}"


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def create_razorpay_order(amount_paise: int, currency: str, receipt: str, notes: dict) -> dict:
    import razorpay

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    return client.order.create(
        data={
            "amount": amount_paise,
            "currency": currency,
            "receipt": str(receipt)[:40],
            "notes": notes,
        }
    )


class PaymentNotFound(Exception):
    pass


def mark_payment_paid(order_id: str, gateway_payment_id: str = ""):
    """
    Idempotently record a successful payment.

    In one transaction: Payment -> paid, Requirement -> converted,
    Matter created (Build Plan Section 10, Step 8). A confirmation e-mail is
    queued after commit.

    Returns (payment, matter, newly_paid: bool).
    """
    from audit.models import StatusChangeLog
    from customer_requirements.models import Requirement, RequirementEvent
    from matters.models import Matter
    from payments.models import Payment

    with transaction.atomic():
        try:
            payment = (
                Payment.objects.select_for_update()
                .select_related("proposal__requirement")
                .get(gateway_order_id=order_id)
            )
        except Payment.DoesNotExist as exc:
            raise PaymentNotFound(order_id) from exc

        proposal = payment.proposal

        if payment.status in (Payment.Status.PAID, Payment.Status.REFUNDED):
            matter = Matter.objects.filter(proposal=proposal).first()
            return payment, matter, False

        payment.status = Payment.Status.PAID
        payment.gateway_payment_id = gateway_payment_id or payment.gateway_payment_id
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "gateway_payment_id", "paid_at"])

        requirement = Requirement.objects.select_for_update().get(pk=proposal.requirement_id)

        if requirement.status in (
            Requirement.Status.PAYMENT_PENDING,
            Requirement.Status.SERVICE_PROPOSED,
        ):
            old_status = requirement.status
            requirement.status = Requirement.Status.CONVERTED
            requirement.save(update_fields=["status", "updated_at"])
            StatusChangeLog.objects.create(
                entity_type="requirement",
                entity_id=str(requirement.pk),
                from_status=old_status,
                to_status=Requirement.Status.CONVERTED,
            )

        RequirementEvent.objects.create(
            requirement=requirement,
            type="PAYMENT_RECEIVED",
            detail=f"{format_inr(to_paise(payment.amount))} · {payment.gateway_payment_id}"[:300],
        )

        matter, _created = Matter.objects.get_or_create(
            proposal=proposal,
            defaults={"status": Matter.Status.ACTIVE},
        )
        if requirement.assigned_professional_id:
            matter.professionals.add(requirement.assigned_professional_id)

        _queue_payment_confirmation(requirement, proposal, matter)

    return payment, matter, True


def mark_payment_failed(order_id: str, reason: str = "") -> None:
    """
    Record a failed attempt on the timeline. The Payment stays *pending* so the
    customer can retry on the same Razorpay order (Razorpay allows retries).
    """
    from customer_requirements.models import RequirementEvent
    from payments.models import Payment

    payment = (
        Payment.objects.select_related("proposal__requirement")
        .filter(gateway_order_id=order_id)
        .first()
    )
    if payment is None or payment.status != Payment.Status.PENDING:
        return
    RequirementEvent.objects.create(
        requirement=payment.proposal.requirement,
        type="PAYMENT_FAILED",
        detail=(reason or "")[:300],
    )


def _queue_payment_confirmation(requirement, proposal, matter) -> None:
    if not requirement.email:
        return

    from matters.tasks import send_status_notification_task

    site = getattr(settings, "SITE_URL", "https://casesuno.in")
    subject = f"CASE SUNO: Payment received - Ref {requirement.reference_id}"
    message = (
        f"Hello {requirement.name},\n\n"
        "Thank you for your payment. Your CASE SUNO request is now active.\n\n"
        f"Service: {proposal.service_name}\n"
        f"Reference ID: {requirement.reference_id}\n"
        f"Matter ID: #{matter.pk}\n\n"
        "Track your request and message our team here:\n"
        f"{site}/track/{requirement.access_token}\n\n"
        "Best regards,\nCASE SUNO Team"
    )
    email = requirement.email

    def _send():
        try:
            send_status_notification_task.delay(
                recipient_email=email,
                subject=subject,
                message=message,
            )
        except Exception:  # never break payment processing because of e-mail
            logger.exception("Could not queue payment confirmation for %s", requirement.reference_id)

    transaction.on_commit(_send)
