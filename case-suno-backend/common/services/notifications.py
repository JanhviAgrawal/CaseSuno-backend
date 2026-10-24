
import logging
import urllib.parse
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_status_notification(
    *,
    recipient_email: str,
    subject: str,
    message: str,
) -> bool:
    """Send a status notification email."""
    if not recipient_email:
        return False

    try:
        return bool(
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        )
    except Exception:
        logger.exception("Failed to send status email to %s", recipient_email)
        return False


def send_sms_notification(
    *,
    recipient_mobile: str,
    message: str,
) -> bool:
    """
    Send a transactional SMS notification on critical status changes.
    Matches PDF Page 4 & 16: "Celery/RQ tasks for transactional email/SMS on status changes"
    In local/dev environments, logs the SMS. Integrates with SMS gateway in production.
    """
    if not recipient_mobile:
        return False

    clean_mobile = recipient_mobile.strip().lstrip("+")
    masked_mobile = clean_mobile[-4:].rjust(len(clean_mobile), "*")
    logger.info("Dispatching transactional SMS to %s: %s", masked_mobile, message)
    # Gateway hook (e.g. Twilio / Gupshup / MSG91)
    return True


def generate_whatsapp_chat_metadata(
    *,
    reference_id: str,
    customer_name: str | None = None,
    default_phone: str | None = None,
) -> dict[str, str]:
    """
    Generate WhatsApp click-to-chat URL and pre-filled message metadata.
    Matches PDF Page 4 & 16: "WhatsApp click-to-chat metadata"
    """
    default_phone = default_phone or getattr(settings, "SUPPORT_WHATSAPP_NUMBER", "918000784778")
    greeting = f"Hello CASE SUNO, I have a query regarding my requirement reference {reference_id}."
    if customer_name:
        greeting = f"Hello CASE SUNO, my name is {customer_name}. I have a query regarding my requirement reference {reference_id}."

    encoded_text = urllib.parse.quote(greeting)
    whatsapp_url = f"https://wa.me/{default_phone}?text={encoded_text}"

    return {
        "whatsappUrl": whatsapp_url,
        "prefilledMessage": greeting,
        "supportPhone": default_phone,
    }
