"""
Website API — everything casesuno.in needs, under /api/web/.

Response convention (matches the Next.js frontend):
    success -> {"ok": true, ...data}
    failure -> {"ok": false, "error": "<human readable message>"}  with an HTTP error status
"""

import hashlib
import logging
import re
import secrets
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AdminSession, AdminUser
from audit.models import StatusChangeLog
from common.permissions.admin_auth import AdminSessionAuthentication, IsAuthenticatedAdmin
from customer_requirements.models import (
    Requirement,
    RequirementMessage,
    RequirementNote,
)
from matters.models import Matter
from payments.models import Payment
from payments.services import (
    PaymentNotFound,
    create_razorpay_order,
    format_inr,
    mark_payment_paid,
    razorpay_configured,
    to_paise,
    verify_checkout_signature,
)
from professionals.models import Professional
from proposals.models import ServiceProposal

from . import services as svc
from .security import FromWebsite, WebsiteRateThrottle

logger = logging.getLogger(__name__)

SESSION_HOURS = 12


def ok(data=None, http_status=status.HTTP_200_OK):
    return Response({"ok": True, **(data or {})}, status=http_status)


def fail(http_status, error):
    return Response({"ok": False, "error": error}, status=http_status)


def _str(data, key, default=""):
    value = data.get(key, default) if isinstance(data, dict) else default
    return value.strip() if isinstance(value, str) else default


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------
class WebAPIView(APIView):
    """Public website endpoint."""

    authentication_classes = []
    permission_classes = [FromWebsite]
    throttle_classes = [WebsiteRateThrottle]
    throttle_scope = None
    throttle_message = "Too many requests. Please try again in a few minutes."

    def get_throttles(self):
        return [t() for t in self.throttle_classes] if self.throttle_scope else []

    def handle_exception(self, exc):
        if isinstance(exc, exceptions.Throttled):
            return fail(status.HTTP_429_TOO_MANY_REQUESTS, self.throttle_message)
        if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
            return fail(status.HTTP_401_UNAUTHORIZED, "Unauthorized")
        if isinstance(exc, exceptions.PermissionDenied):
            return fail(status.HTTP_403_FORBIDDEN, "Forbidden")
        if isinstance(exc, exceptions.ParseError):
            return fail(status.HTTP_400_BAD_REQUEST, "Invalid request")
        if isinstance(exc, exceptions.MethodNotAllowed):
            return fail(status.HTTP_405_METHOD_NOT_ALLOWED, "Method not allowed")
        return super().handle_exception(exc)


class AdminWebAPIView(WebAPIView):
    """Admin endpoint — requires a valid admin session token."""

    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [FromWebsite, IsAuthenticatedAdmin]

    def permission_denied(self, request, message=None, code=None):
        if request.authenticators and not request.successful_authenticator:
            raise exceptions.NotAuthenticated()
        raise exceptions.PermissionDenied()


# ---------------------------------------------------------------------------
# Public: enquiry intake
# ---------------------------------------------------------------------------
def _next_reference_id() -> str:
    """CS-<year>-<5 digit sequence>, e.g. CS-2026-00042 (same format as the Build Plan API)."""
    for _ in range(20):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT nextval('customer_requirements_reference_seq')")
                number = cursor.fetchone()[0]
        else:  # pragma: no cover - non-Postgres fallback
            number = (Requirement.objects.order_by("-pk").values_list("pk", flat=True).first() or 0) + 1
        reference = f"CS-{timezone.now().year}-{number:05d}"
        if not Requirement.objects.filter(reference_id=reference).exists():
            return reference
    return f"CS-{timezone.now().year}-{secrets.token_hex(3).upper()}"


class EnquiryCreateView(WebAPIView):
    throttle_scope = "web_enquiry"

    def post(self, request):
        d = request.data if isinstance(request.data, dict) else {}

        # Honeypot: bots fill the hidden "website" field — pretend success, store nothing
        if _str(d, "website"):
            return ok({"reference": "CS-RECEIVED", "token": ""})

        category = _str(d, "category")
        description = _str(d, "description")
        full_name = _str(d, "fullName")
        phone = _str(d, "phone")
        email = _str(d, "email")
        city = _str(d, "city")
        language = _str(d, "language") or "en"

        if not (1 <= len(category) <= 120) or not (5 <= len(description) <= 1500) \
                or not (2 <= len(full_name) <= 120) or not (8 <= len(phone) <= 20) \
                or len(email) > 160 or len(city) > 120 or language not in ("en", "hi", "gu"):
            return fail(400, "Please check the form details.")

        digits = re.sub(r"\D", "", phone)
        if len(digits) < 10 or len(digits) > 13:
            return fail(400, "Please enter a valid mobile number.")

        if email:
            try:
                validate_email(email)
            except DjangoValidationError:
                return fail(400, "Please enter a valid email address.")

        try:
            with transaction.atomic():
                requirement = Requirement.objects.create(
                    reference_id=_next_reference_id(),
                    name=full_name,
                    mobile=phone,
                    email=email,
                    city=city,
                    requirement_type=category,
                    description=description,
                    language=language,
                    consent_given=True,
                )
                svc.add_event(requirement, "CREATED")
                StatusChangeLog.objects.create(
                    entity_type="requirement",
                    entity_id=str(requirement.pk),
                    from_status="",
                    to_status=requirement.status,
                )
        except Exception:
            logger.exception("Enquiry create failed")
            return fail(500, "Could not save your enquiry. Please try again.")

        link = svc.track_url(requirement)
        svc.notify(
            requirement.email,
            f"CASE SUNO: Enquiry received - Ref {requirement.reference_id}",
            (
                f"Hello {requirement.name},\n\n"
                "Thank you for contacting CASE SUNO. We have received your enquiry and a "
                "coordinator will review it shortly.\n\n"
                f"Reference: {requirement.reference_id}\n"
                f"Category: {requirement.requirement_type}\n\n"
                f"Track your request and reply to our team here:\n{link}\n\n"
                "Please keep this link private.\n\nCASE SUNO Team"
            ),
        )
        svc.notify_admins(
            f"New enquiry {requirement.reference_id} — {requirement.requirement_type}",
            (
                f"Name: {requirement.name}\nPhone: {requirement.mobile}\n"
                f"Email: {requirement.email or '-'}\nCity: {requirement.city or '-'}\n"
                f"Category: {requirement.requirement_type}\n\n{requirement.description}\n"
            ),
        )

        return ok(
            {"reference": requirement.reference_id, "token": requirement.access_token},
            http_status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Public: tracking
# ---------------------------------------------------------------------------
class TrackLookupView(WebAPIView):
    throttle_scope = "web_lookup"
    throttle_message = "Too many attempts. Please try again in a few minutes."

    def post(self, request):
        d = request.data if isinstance(request.data, dict) else {}
        reference = re.sub(r"\s+", "", _str(d, "reference"))
        phone = _str(d, "phone")

        if not (3 <= len(reference) <= 40) or not (8 <= len(phone) <= 20):
            return fail(400, "Please enter your reference number and mobile number.")

        requirement = Requirement.objects.filter(reference_id__iexact=reference).first()

        # Same message for "not found" and "wrong phone" so details can't be probed
        if requirement is None or svc.last10(requirement.mobile) != svc.last10(phone):
            return fail(404, "No request found with these details. Please check and try again.")

        return ok({"token": requirement.access_token})


def _requirement_by_token(token):
    if not token or len(token) > 64:
        return None
    return (
        Requirement.objects.select_related("assigned_professional", "proposal", "proposal__payment")
        .filter(access_token=token)
        .first()
    )


class TrackDetailView(WebAPIView):
    throttle_scope = None

    def get(self, request, token):
        r = _requirement_by_token(token)
        if r is None:
            return fail(404, "Not found")

        payment = svc.get_payment(r)
        paid = None
        if payment and payment.status == Payment.Status.PAID:
            paid = {
                "amount": to_paise(payment.amount),
                "paidAt": svc.iso(payment.paid_at or payment.created_at),
            }

        lawyer = None
        if r.share_professional_with_customer and r.assigned_professional:
            p = r.assigned_professional
            lawyer = {
                "name": p.name,
                "phone": p.phone or p.contact,
                "email": p.email or None,
                "specialization": p.specialism,
            }

        return ok(
            {
                "reference": r.reference_id,
                "category": r.requirement_type,
                "fullName": r.name,
                "status": svc.web_status(r.status),
                "feeAmount": r.fee_amount_paise,
                "createdAt": svc.iso(r.created_at),
                "paymentEnabled": razorpay_configured(),
                "paid": paid,
                "lawyer": lawyer,
                "messages": [
                    {"id": str(m.pk), "sender": m.sender, "body": m.body, "createdAt": svc.iso(m.created_at)}
                    for m in r.messages.all().order_by("created_at", "pk")
                ],
            }
        )


class TrackMessageView(WebAPIView):
    throttle_scope = "web_message"
    throttle_message = "Too many messages. Please wait a moment."

    def post(self, request, token):
        body = _str(request.data if isinstance(request.data, dict) else {}, "body")
        if not (1 <= len(body) <= 2000):
            return fail(400, "Message cannot be empty")

        r = _requirement_by_token(token)
        if r is None:
            return fail(404, "Not found")
        if r.status in (Requirement.Status.CLOSED, Requirement.Status.REJECTED):
            return fail(409, "This request is closed.")

        with transaction.atomic():
            RequirementMessage.objects.create(
                requirement=r,
                sender=RequirementMessage.Sender.CLIENT,
                body=body,
            )
            svc.add_event(r, "CLIENT_MESSAGE")

        svc.notify_admins(
            f"Client replied on {r.reference_id}",
            f"{r.name} ({r.mobile}) wrote:\n\n{body}\n",
        )
        return ok(http_status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Public: checkout
# ---------------------------------------------------------------------------
class CreateOrderView(WebAPIView):
    throttle_scope = "web_order"
    throttle_message = "Too many attempts. Please wait a moment."

    def post(self, request):
        token = _str(request.data if isinstance(request.data, dict) else {}, "token")
        if not (10 <= len(token) <= 100):
            return fail(400, "Invalid request")

        r = _requirement_by_token(token)
        if r is None:
            return fail(404, "Request not found")

        proposal = getattr(r, "proposal", None)
        if (
            r.status not in (Requirement.Status.PAYMENT_PENDING, Requirement.Status.SERVICE_PROPOSED)
            or not r.fee_amount_paise
            or proposal is None
        ):
            return fail(409, "No payment is due right now.")
        if not razorpay_configured():
            return fail(503, "Online payment is not available right now.")

        amount_paise = to_paise(proposal.fee)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(proposal=proposal).first()

            if payment and payment.status == Payment.Status.PAID:
                return fail(409, "The platform fee has already been paid for this request.")

            # Reuse an open order for the same amount, otherwise create a new one
            if payment is None or to_paise(payment.amount) != amount_paise:
                try:
                    order = create_razorpay_order(
                        amount_paise,
                        proposal.currency,
                        r.reference_id,
                        {"proposal_id": str(proposal.public_id), "reference": r.reference_id},
                    )
                except Exception:
                    logger.exception("Razorpay order creation failed for %s", r.reference_id)
                    return fail(502, "Could not start the payment. Please try again.")

                if payment is None:
                    payment = Payment.objects.create(
                        proposal=proposal,
                        gateway_order_id=order["id"],
                        amount=proposal.fee,
                        status=Payment.Status.PENDING,
                    )
                else:
                    payment.gateway_order_id = order["id"]
                    payment.amount = proposal.fee
                    payment.status = Payment.Status.PENDING
                    payment.gateway_payment_id = ""
                    payment.save(update_fields=["gateway_order_id", "amount", "status", "gateway_payment_id"])

        from django.conf import settings

        return ok(
            {
                "orderId": payment.gateway_order_id,
                "amount": amount_paise,
                "currency": proposal.currency,
                "keyId": settings.RAZORPAY_KEY_ID,
                "reference": r.reference_id,
                "prefill": {"name": r.name, "email": r.email or "", "contact": r.mobile},
            }
        )


class VerifyPaymentView(WebAPIView):
    throttle_scope = "web_order"

    def post(self, request):
        d = request.data if isinstance(request.data, dict) else {}
        order_id = _str(d, "razorpay_order_id")
        payment_id = _str(d, "razorpay_payment_id")
        signature = _str(d, "razorpay_signature")

        if not (order_id and payment_id and signature):
            return fail(400, "Invalid payment data")
        if not verify_checkout_signature(order_id, payment_id, signature):
            return fail(400, "Payment verification failed")

        try:
            mark_payment_paid(order_id, payment_id)
        except PaymentNotFound:
            return fail(404, "Payment not found")
        return ok()


# ---------------------------------------------------------------------------
# Admin: authentication
# ---------------------------------------------------------------------------
class AdminLoginView(WebAPIView):
    throttle_scope = "web_login"
    throttle_message = "Too many attempts. Please try again later."

    def post(self, request):
        d = request.data if isinstance(request.data, dict) else {}
        email = _str(d, "email").lower()
        password = d.get("password") if isinstance(d.get("password"), str) else ""

        admin = (
            AdminUser.objects.select_related("user")
            .filter(email__iexact=email, is_active=True)
            .first()
        )
        user = admin.user if admin else None
        valid = bool(
            admin and user and user.is_active and password and user.check_password(password)
        )
        if not valid:
            # Constant-ish time and a small delay to slow down guessing
            check_password(password or "x", "pbkdf2_sha256$1$x$x")
            time.sleep(0.6)
            return fail(401, "Invalid email or password.")

        raw_token = secrets.token_urlsafe(32)
        AdminSession.objects.create(
            admin_user=admin,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=timezone.now() + timedelta(hours=SESSION_HOURS),
        )
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        return ok(
            {
                "token": raw_token,
                "maxAge": SESSION_HOURS * 3600,
                "email": admin.email,
                "name": admin.name,
            }
        )


class AdminLogoutView(AdminWebAPIView):
    def post(self, request):
        if isinstance(request.auth, AdminSession):
            request.auth.revoked_at = timezone.now()
            request.auth.save(update_fields=["revoked_at"])
        return ok()


def _unread_total() -> int:
    return RequirementMessage.objects.filter(
        sender=RequirementMessage.Sender.CLIENT, read_by_admin=False
    ).count()


class AdminMeView(AdminWebAPIView):
    def get(self, request):
        return ok(
            {
                "email": request.user.email,
                "name": request.user.name,
                "role": request.user.role,
                "unread": _unread_total(),
            }
        )


# ---------------------------------------------------------------------------
# Admin: dashboard
# ---------------------------------------------------------------------------
def _web_status_counts(queryset) -> dict:
    counts = {code: 0 for code in svc.WEB_STATUSES}
    for row in queryset.values("status").annotate(n=Count("id")):
        counts[svc.web_status(row["status"])] += row["n"]
    return counts


class AdminDashboardView(AdminWebAPIView):
    def get(self, request):
        since = timezone.localtime() - timedelta(days=13)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)

        reqs = Requirement.objects.all()
        unread_q = Count(
            "messages",
            filter=Q(messages__sender="CLIENT", messages__read_by_admin=False),
        )

        recent = reqs.annotate(unread=unread_q).order_by("-created_at")[:6]
        categories = (
            reqs.values("requirement_type")
            .annotate(n=Count("id"))
            .order_by("-n", "requirement_type")[:8]
        )
        revenue = Payment.objects.filter(status=Payment.Status.PAID).aggregate(s=Sum("amount"))["s"] or Decimal("0")

        return ok(
            {
                "total": reqs.count(),
                "statusCounts": _web_status_counts(reqs),
                "categories": [{"category": c["requirement_type"], "count": c["n"]} for c in categories],
                "revenue": to_paise(revenue),
                "recent": [svc.enquiry_summary_json(r, r.unread) for r in recent],
                "lastDays": [
                    svc.iso(dt)
                    for dt in reqs.filter(created_at__gte=since).values_list("created_at", flat=True)
                ],
                "unread": _unread_total(),
                "paidCount": reqs.filter(proposal__payment__status=Payment.Status.PAID).distinct().count(),
                "requestedCount": reqs.filter(fee_amount_paise__isnull=False).count(),
            }
        )


# ---------------------------------------------------------------------------
# Admin: enquiries
# ---------------------------------------------------------------------------
class AdminEnquiryListView(AdminWebAPIView):
    PAGE_SIZE = 20

    def get(self, request):
        status_code = request.query_params.get("status", "")
        q = (request.query_params.get("q") or "").strip()[:100]
        try:
            page = max(1, int(request.query_params.get("page") or 1))
        except ValueError:
            page = 1

        searched = Requirement.objects.all()
        if q:
            searched = searched.filter(
                Q(reference_id__icontains=q)
                | Q(name__icontains=q)
                | Q(mobile__icontains=q)
                | Q(requirement_type__icontains=q)
                | Q(description__icontains=q)
            )

        filtered = searched
        if status_code in svc.WEB_STATUSES:
            filtered = filtered.filter(status__in=svc.db_statuses_for(status_code))

        count = filtered.count()
        items = (
            filtered.annotate(
                unread=Count(
                    "messages",
                    filter=Q(messages__sender="CLIENT", messages__read_by_admin=False),
                )
            )
            .order_by("-created_at")[(page - 1) * self.PAGE_SIZE: page * self.PAGE_SIZE]
        )

        return ok(
            {
                "items": [svc.enquiry_summary_json(r, r.unread) for r in items],
                "count": count,
                "page": page,
                "pageSize": self.PAGE_SIZE,
                "statusCounts": _web_status_counts(searched),
            }
        )


def _get_requirement(pk):
    try:
        return Requirement.objects.select_related(
            "assigned_professional", "proposal", "proposal__payment"
        ).get(pk=int(pk))
    except (Requirement.DoesNotExist, ValueError, TypeError):
        return None


def _set_status(r, target_db_status, admin, events):
    old = r.status
    if old == target_db_status:
        return
    r.status = target_db_status
    events.append(
        ("STATUS_CHANGED", f"{svc.STATUS_LABELS[svc.web_status(old)]} → {svc.STATUS_LABELS[svc.web_status(target_db_status)]}")
    )
    StatusChangeLog.objects.create(
        entity_type="requirement",
        entity_id=str(r.pk),
        from_status=old,
        to_status=target_db_status,
        admin_user=admin if isinstance(admin, AdminUser) else None,
    )
    if target_db_status == Requirement.Status.REVIEWED and isinstance(admin, AdminUser) and not r.reviewed_by_id:
        r.reviewed_by = admin


def _sync_matter_professional(r):
    """Keep the Matter's professionals in line with the assigned lawyer."""
    proposal = getattr(r, "proposal", None)
    matter = Matter.objects.filter(proposal=proposal).first() if proposal else None
    if matter is None:
        return
    if r.assigned_professional_id:
        matter.professionals.set([r.assigned_professional_id])
    else:
        matter.professionals.clear()


class AdminEnquiryDetailView(AdminWebAPIView):
    def get(self, request, pk):
        r = _get_requirement(pk)
        if r is None:
            return fail(404, "Request not found")

        # Opening a request marks client replies as read
        r.messages.filter(sender="CLIENT", read_by_admin=False).update(read_by_admin=True)

        lawyers = Professional.objects.filter(
            Q(is_active=True) | Q(pk=r.assigned_professional_id or 0)
        ).order_by("name")

        return ok(
            {
                "enquiry": svc.enquiry_detail_json(r),
                "lawyers": [svc.professional_json(p) for p in lawyers],
            }
        )

    def patch(self, request, pk):
        d = request.data if isinstance(request.data, dict) else {}

        st = d.get("status")
        pr = d.get("priority")
        ha = d.get("handling")
        if (st is not None and st not in svc.WEB_STATUSES) \
                or (pr is not None and pr not in svc.WEB_PRIORITIES) \
                or (ha is not None and ha not in svc.WEB_HANDLING) \
                or ("shareLawyerWithClient" in d and not isinstance(d["shareLawyerWithClient"], bool)):
            return fail(400, "Invalid data")

        with transaction.atomic():
            r = Requirement.objects.select_for_update().filter(pk=pk if str(pk).isdigit() else 0).first()
            if r is None:
                return fail(404, "Request not found")

            events = []

            if st is not None:
                _set_status(r, svc.WEB_TO_DB_STATUS[st], request.user, events)

            if pr is not None and svc.WEB_TO_DB_PRIORITY[pr] != r.urgency:
                events.append(
                    ("PRIORITY_CHANGED", f"{svc.PRIORITY_LABELS[svc.web_priority(r.urgency)]} → {svc.PRIORITY_LABELS[pr]}")
                )
                r.urgency = svc.WEB_TO_DB_PRIORITY[pr]

            if ha is not None and svc.WEB_TO_DB_HANDLING[ha] != r.handling:
                r.handling = svc.WEB_TO_DB_HANDLING[ha]
                events.append(("HANDLING_CHANGED", svc.HANDLING_LABELS[ha]))

            lawyer_changed = False
            if "lawyerId" in d:
                lawyer_id = d.get("lawyerId")
                if lawyer_id in (None, ""):
                    if r.assigned_professional_id:
                        r.assigned_professional = None
                        events.append(("LAWYER_REMOVED", ""))
                        lawyer_changed = True
                else:
                    lawyer = Professional.objects.filter(pk=lawyer_id if str(lawyer_id).isdigit() else 0).first()
                    if lawyer is None:
                        return fail(400, "Lawyer not found")
                    if lawyer.pk != r.assigned_professional_id:
                        r.assigned_professional = lawyer
                        events.append(("LAWYER_ASSIGNED", f"{lawyer.name} ({lawyer.specialism})"))
                        lawyer_changed = True

            if "shareLawyerWithClient" in d and d["shareLawyerWithClient"] != r.share_professional_with_customer:
                r.share_professional_with_customer = d["shareLawyerWithClient"]
                events.append(
                    ("SHARE_CHANGED", "Visible to client" if r.share_professional_with_customer else "Hidden from client")
                )

            if not events:
                return ok()

            r.save()
            for type_, detail in events:
                svc.add_event(r, type_, detail)
            if lawyer_changed:
                _sync_matter_professional(r)

        return ok()


class AdminEnquiryMessageView(AdminWebAPIView):
    def post(self, request, pk):
        body = _str(request.data if isinstance(request.data, dict) else {}, "body")
        if not (1 <= len(body) <= 4000):
            return fail(400, "Message cannot be empty")

        with transaction.atomic():
            r = Requirement.objects.select_for_update().filter(pk=pk if str(pk).isdigit() else 0).first()
            if r is None:
                return fail(404, "Request not found")

            RequirementMessage.objects.create(
                requirement=r,
                sender=RequirementMessage.Sender.ADMIN,
                body=body,
                read_by_admin=True,
            )
            svc.add_event(r, "ADMIN_REPLY")

            if r.status == Requirement.Status.NEW:
                events = []
                _set_status(r, Requirement.Status.REVIEWED, request.user, events)
                r.save()
                for type_, detail in events:
                    svc.add_event(r, type_, detail)

        svc.notify(
            r.email,
            f"CASE SUNO: New message on your request {r.reference_id}",
            f"Hello {r.name},\n\n{body}\n\nView your request and reply here:\n{svc.track_url(r)}\n\nCASE SUNO Team",
        )
        return ok(http_status=status.HTTP_201_CREATED)


class AdminEnquiryNoteView(AdminWebAPIView):
    def post(self, request, pk):
        body = _str(request.data if isinstance(request.data, dict) else {}, "body")
        if not (1 <= len(body) <= 4000):
            return fail(400, "Note cannot be empty")

        r = _get_requirement(pk)
        if r is None:
            return fail(404, "Request not found")

        with transaction.atomic():
            RequirementNote.objects.create(requirement=r, body=body, author=request.user)
            svc.add_event(r, "NOTE_ADDED")
        return ok(http_status=status.HTTP_201_CREATED)


class AdminRequestPaymentView(AdminWebAPIView):
    MAX_RUPEES = Decimal("500000")

    def post(self, request, pk):
        d = request.data if isinstance(request.data, dict) else {}
        message = _str(d, "message")
        note = _str(d, "note")
        try:
            rupees = Decimal(str(d.get("amountRupees"))).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            rupees = Decimal("0")

        if rupees <= 0 or rupees > self.MAX_RUPEES or not (1 <= len(message) <= 4000) or len(note) > 300:
            return fail(400, "Enter a valid amount and message")

        with transaction.atomic():
            r = Requirement.objects.select_for_update().filter(pk=pk if str(pk).isdigit() else 0).first()
            if r is None:
                return fail(404, "Request not found")

            proposal = ServiceProposal.objects.select_for_update().filter(requirement=r).first()
            payment = Payment.objects.select_for_update().filter(proposal=proposal).first() if proposal else None
            if payment and payment.status in (Payment.Status.PAID, Payment.Status.REFUNDED):
                return fail(409, "The platform fee has already been paid for this request.")

            service_name = (note or "CASE SUNO platform fee")[:200]
            valid_until = timezone.localdate() + timedelta(days=30)

            if proposal is None:
                proposal = ServiceProposal.objects.create(
                    requirement=r,
                    service_name=service_name,
                    scope=message,
                    fee=rupees,
                    currency="INR",
                    valid_until=valid_until,
                )
            else:
                proposal.service_name = service_name
                proposal.scope = message
                proposal.fee = rupees
                proposal.valid_until = valid_until
                proposal.save(update_fields=["service_name", "scope", "fee", "valid_until"])
                # An unpaid order for a different amount is discarded; a new one is created at checkout
                if payment and to_paise(payment.amount) != to_paise(rupees):
                    payment.delete()

            amount_paise = to_paise(rupees)
            r.fee_amount_paise = amount_paise
            r.fee_note = note
            events = []
            _set_status(r, Requirement.Status.PAYMENT_PENDING, request.user, events)
            r.save()

            RequirementMessage.objects.create(
                requirement=r,
                sender=RequirementMessage.Sender.ADMIN,
                body=message,
                read_by_admin=True,
            )
            for type_, detail in events:
                svc.add_event(r, type_, detail)
            svc.add_event(r, "PAYMENT_REQUESTED", format_inr(amount_paise))

        svc.notify(
            r.email,
            f"CASE SUNO: Platform fee for your request {r.reference_id}",
            f"Hello {r.name},\n\n{message}\n\nPay securely and view updates here:\n{svc.track_url(r)}\n\nCASE SUNO Team",
        )
        return ok(http_status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Admin: lawyers / professionals
# ---------------------------------------------------------------------------
def _validate_lawyer_fields(d, partial=False):
    """Returns (clean_fields, error)."""
    rules = {
        "name": (2, 120, True),
        "phone": (8, 20, True),
        "specialization": (2, 160, True),
        "email": (0, 160, False),
        "city": (0, 120, False),
    }
    clean = {}
    for key, (lo, hi, required) in rules.items():
        if key not in d:
            if required and not partial:
                return None, "Please fill name, phone and specialization"
            continue
        value = d.get(key)
        if value is None and not required:
            value = ""
        if not isinstance(value, str):
            return None, "Invalid data"
        value = value.strip()
        if len(value) > hi or (required and len(value) < lo):
            return None, "Please fill name, phone and specialization" if not partial else "Invalid data"
        clean[key] = value

    if clean.get("email"):
        try:
            validate_email(clean["email"])
        except DjangoValidationError:
            return None, "Please enter a valid email address"
    return clean, None


def _apply_lawyer_fields(p, clean):
    mapping = {"name": "name", "phone": "phone", "email": "email", "specialization": "specialism", "city": "city"}
    for key, attr in mapping.items():
        if key in clean:
            setattr(p, attr, clean[key])
    if "phone" in clean or "email" in clean:
        p.contact = " / ".join(v for v in (p.phone, p.email) if v)


class AdminLawyerListView(AdminWebAPIView):
    def get(self, request):
        lawyers = Professional.objects.annotate(cases=Count("requirements")).order_by("-is_active", "name")
        return ok({"lawyers": [{**svc.professional_json(p), "cases": p.cases} for p in lawyers]})

    def post(self, request):
        d = request.data if isinstance(request.data, dict) else {}
        clean, error = _validate_lawyer_fields(d)
        if error:
            return fail(400, error)
        p = Professional(is_active=True)
        _apply_lawyer_fields(p, clean)
        p.save()
        return ok({"id": str(p.pk)}, http_status=status.HTTP_201_CREATED)


class AdminLawyerDetailView(AdminWebAPIView):
    def patch(self, request, pk):
        d = request.data if isinstance(request.data, dict) else {}
        p = Professional.objects.filter(pk=pk if str(pk).isdigit() else 0).first()
        if p is None:
            return fail(404, "Lawyer not found")

        if "active" in d and not isinstance(d["active"], bool):
            return fail(400, "Invalid data")
        clean, error = _validate_lawyer_fields(d, partial=True)
        if error:
            return fail(400, error)

        _apply_lawyer_fields(p, clean)
        if "active" in d:
            p.is_active = d["active"]
        p.save()
        return ok()


# ---------------------------------------------------------------------------
# Admin: payments
# ---------------------------------------------------------------------------
class AdminPaymentListView(AdminWebAPIView):
    def get(self, request):
        payments = (
            Payment.objects.select_related("proposal__requirement")
            .order_by("-created_at")[:200]
        )
        paid = Payment.objects.filter(status=Payment.Status.PAID).aggregate(s=Sum("amount"), n=Count("id"))
        return ok(
            {
                "payments": [
                    {
                        **svc.payment_json(p),
                        "enquiry": {
                            "id": str(p.proposal.requirement.pk),
                            "reference": p.proposal.requirement.reference_id,
                            "fullName": p.proposal.requirement.name,
                        },
                    }
                    for p in payments
                ],
                "paidSum": to_paise(paid["s"] or Decimal("0")),
                "paidCount": paid["n"] or 0,
            }
        )
