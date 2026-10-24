try:  # Celery is optional at runtime: without a broker, tasks run inline.
    from .celery import app as celery_app
except ImportError:  # pragma: no cover
    celery_app = None

__all__ = ("celery_app",)
