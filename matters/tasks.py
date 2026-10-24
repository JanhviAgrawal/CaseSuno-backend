
import smtplib

try:
    from celery import shared_task
except ImportError:  # pragma: no cover - Celery not installed: run tasks inline
    def shared_task(*dargs, **dkwargs):
        def wrap(func):
            func.delay = lambda *a, **kw: func(*a, **kw)
            func.apply_async = lambda args=(), kwargs=None, **_: func(*args, **(kwargs or {}))
            return func
        if dargs and callable(dargs[0]) and not dkwargs:
            return wrap(dargs[0])
        return wrap

from common.services.notifications import (
    send_status_notification,
    send_sms_notification,
)


@shared_task(
    name="matters.send_status_notification",
    autoretry_for=(smtplib.SMTPException, OSError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_status_notification_task(
    *,
    recipient_email: str,
    subject: str,
    message: str,
) -> bool:
    """Send a CASE SUNO status notification asynchronously."""
    return send_status_notification(
        recipient_email=recipient_email,
        subject=subject,
        message=message,
    )


@shared_task(
    name="matters.send_sms_notification",
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_sms_notification_task(
    *,
    recipient_mobile: str,
    message: str,
) -> bool:
    """Send a transactional SMS notification asynchronously on critical status changes."""
    return send_sms_notification(
        recipient_mobile=recipient_mobile,
        message=message,
    )
