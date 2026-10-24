"""
Mapping between the website's vocabulary (UPPER_CASE codes used by the
Next.js frontend) and the backend models, plus the JSON shapes the
frontend components expect.
"""

import logging
import re

from django.conf import settings
from django.db import transaction

from customer_requirements.models import Requirement, RequirementEvent
from payments.services import to_paise

logger = logging.getLogger(__name__)

S = Requirement.Status

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
WEB_STATUSES = [
    "NEW",
    "IN_REVIEW",
    "AWAITING_PAYMENT",
    "PAID",
    "IN_PROGRESS",
    "FORWARDED",
    "RESOLVED",
    "CLOSED",
    "REJECTED",
]

# website code -> value stored in the database
WEB_TO_DB_STATUS = {
    "NEW": S.NEW,
    "IN_REVIEW": S.REVIEWED,
    "AWAITING_PAYMENT": S.PAYMENT_PENDING,
    "PAID": S.CONVERTED,
    "IN_PROGRESS": S.IN_PROGRESS,
    "FORWARDED": S.FORWARDED,
    "RESOLVED": S.RESOLVED,
    "CLOSED": S.CLOSED,
    "REJECTED": S.REJECTED,
}

# database value -> website code (Build Plan intermediate stages fold into the nearest website stage)
DB_TO_WEB_STATUS = {
    S.NEW: "NEW",
    S.CONTACTED: "IN_REVIEW",
    S.INFORMATION_RECEIVED: "IN_REVIEW",
    S.REVIEWED: "IN_REVIEW",
    S.SERVICE_PROPOSED: "AWAITING_PAYMENT",
    S.PAYMENT_PENDING: "AWAITING_PAYMENT",
    S.CONVERTED: "PAID",
    S.IN_PROGRESS: "IN_PROGRESS",
    S.FORWARDED: "FORWARDED",
    S.RESOLVED: "RESOLVED",
    S.CLOSED: "CLOSED",
    S.REJECTED: "REJECTED",
}

STATUS_LABELS = {
    "NEW": "New",
    "IN_REVIEW": "In review",
    "AWAITING_PAYMENT": "Awaiting payment",
    "PAID": "Fee paid",
    "IN_PROGRESS": "In progress (in-house)",
    "FORWARDED": "Forwarded to lawyer",
    "RESOLVED": "Resolved",
    "CLOSED": "Closed",
    "REJECTED": "Not serviceable",
}


def web_status(db_value: str) -> str:
    return DB_TO_WEB_STATUS.get(db_value, "NEW")


def db_statuses_for(web_code: str) -> list[str]:
    """All database values that display as the given website status."""
    return [db for db, web in DB_TO_WEB_STATUS.items() if web == web_code]


# ---------------------------------------------------------------------------
# Priority (stored in Requirement.urgency)
# ---------------------------------------------------------------------------
U = Requirement.Urgency
WEB_PRIORITIES = ["LOW", "NORMAL", "HIGH", "URGENT"]
WEB_TO_DB_PRIORITY = {"LOW": U.LOW, "NORMAL": U.MEDIUM, "HIGH": U.HIGH, "URGENT": U.URGENT}
DB_TO_WEB_PRIORITY = {v: k for k, v in WEB_TO_DB_PRIORITY.items()}
PRIORITY_LABELS = {"LOW": "Low", "NORMAL": "Normal", "HIGH": "High", "URGENT": "Urgent"}


def web_priority(db_value: str) -> str:
    return DB_TO_WEB_PRIORITY.get(db_value, "NORMAL")


# ---------------------------------------------------------------------------
# Handling
# ---------------------------------------------------------------------------
H = Requirement.Handling
WEB_HANDLING = ["UNDECIDED", "IN_HOUSE", "LAWYER"]
WEB_TO_DB_HANDLING = {"UNDECIDED": H.UNDECIDED, "IN_HOUSE": H.IN_HOUSE, "LAWYER": H.LAWYER}
DB_TO_WEB_HANDLING = {v: k for k, v in WEB_TO_DB_HANDLING.items()}
HANDLING_LABELS = {"UNDECIDED": "Undecided", "IN_HOUSE": "Managed in-house", "LAWYER": "Forward to lawyer"}


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
PAYMENT_STATUS = {"pending": "CREATED", "paid": "PAID", "failed": "FAILED", "refunded": "REFUNDED"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def iso(dt):
    return dt.isoformat() if dt else None


def last10(value: str) -> str:
    return re.sub(r"\D", "", value or "")[-10:]


def add_event(requirement, type_: str, detail: str = "") -> RequirementEvent:
    return RequirementEvent.objects.create(
        requirement=requirement,
        type=type_,
        detail=(detail or "")[:300],
    )


def get_payment(requirement):
    """The Payment attached to this requirement's proposal (or None)."""
    proposal = getattr(requirement, "proposal", None)
    if proposal is None:
        return None
    return getattr(proposal, "payment", None)


def professional_json(p) -> dict:
    return {
        "id": str(p.pk),
        "name": p.name,
        "phone": p.phone or p.contact,
        "email": p.email or None,
        "specialization": p.specialism,
        "city": p.city or None,
        "active": p.is_active,
    }


def payment_json(payment) -> dict:
    return {
        "id": str(payment.pk),
        "amount": to_paise(payment.amount),
        "status": PAYMENT_STATUS.get(payment.status, payment.status.upper()),
        "razorpayOrderId": payment.gateway_order_id,
        "razorpayPaymentId": payment.gateway_payment_id or None,
        "createdAt": iso(payment.created_at),
        "paidAt": iso(payment.paid_at),
    }


def enquiry_summary_json(r, unread: int = 0) -> dict:
    return {
        "id": str(r.pk),
        "reference": r.reference_id,
        "fullName": r.name,
        "phone": r.mobile,
        "category": r.requirement_type,
        "description": r.description,
        "status": web_status(r.status),
        "priority": web_priority(r.urgency),
        "createdAt": iso(r.created_at),
        "unread": unread,
    }


def enquiry_detail_json(r) -> dict:
    payment = get_payment(r)
    return {
        "id": str(r.pk),
        "reference": r.reference_id,
        "accessToken": r.access_token,
        "category": r.requirement_type,
        "description": r.description,
        "fullName": r.name,
        "phone": r.mobile,
        "email": r.email or None,
        "city": r.city or None,
        "language": r.language,
        "status": web_status(r.status),
        "priority": web_priority(r.urgency),
        "handling": DB_TO_WEB_HANDLING.get(r.handling, "UNDECIDED"),
        "feeAmount": r.fee_amount_paise,
        "feeNote": r.fee_note or None,
        "lawyerId": str(r.assigned_professional_id) if r.assigned_professional_id else None,
        "shareLawyerWithClient": r.share_professional_with_customer,
        "createdAt": iso(r.created_at),
        "messages": [
            {"id": str(m.pk), "sender": m.sender, "body": m.body, "createdAt": iso(m.created_at)}
            for m in r.messages.all().order_by("created_at", "pk")
        ],
        "notes": [
            {"id": str(n.pk), "body": n.body, "createdAt": iso(n.created_at)}
            for n in r.notes.all().order_by("-created_at", "-pk")
        ],
        "events": [
            {"id": str(e.pk), "type": e.type, "detail": e.detail or None, "createdAt": iso(e.created_at)}
            for e in r.events.all().order_by("-created_at", "-pk")
        ],
        "payments": [payment_json(payment)] if payment else [],
    }


def track_url(requirement) -> str:
    return f"{settings.SITE_URL}/track/{requirement.access_token}"


# ---------------------------------------------------------------------------
# E-mail notifications (best effort, never break the request)
# ---------------------------------------------------------------------------
def notify(recipient: str, subject: str, message: str) -> None:
    if not recipient:
        return

    from matters.tasks import send_status_notification_task

    def _send():
        try:
            send_status_notification_task.delay(
                recipient_email=recipient,
                subject=subject,
                message=message,
            )
        except Exception:
            logger.exception("Could not queue e-mail to %s", recipient)

    transaction.on_commit(_send)


def notify_admins(subject: str, message: str) -> None:
    for email in getattr(settings, "ADMIN_NOTIFY_EMAILS", []) or []:
        notify(email, subject, message)
